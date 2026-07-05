# Parametricus

Software de design assistido por computador (CAD) com enfoque em **modelagem paramétrica 3D**, escrito em Python puro sobre NumPy. A geometria é representada por **campos de distância assinada (SDF)** — a mesma técnica de kernels implícitos modernos — o que torna operações booleanas, filetes e cascas numericamente robustas e faz com que **todo o modelo se regenere automaticamente quando um parâmetro muda**.

## Instalação

```bash
pip install numpy scikit-image matplotlib
```

Coloque a pasta `parametricus/` no seu projeto (ou adicione ao `PYTHONPATH`).

## Conceitos

| Conceito | Módulo | Papel |
|---|---|---|
| `ParameterSet` | `parameters.py` | Parâmetros nomeados com **expressões** (`"L/2"`, `"max(a,b)*0.1"`), grafo de dependências, detecção de ciclos e reavaliação em cascata. |
| `SDF` e subclasses | `sdf.py` | Árvore de construção (CSG): primitivas, booleanas, transformações e operações de engenharia. Dimensões podem ser *lambdas* ligadas aos parâmetros. |
| `Profile` | `sketch.py` | Esboços 2D (círculo, retângulo, polígono, polígono regular) com booleanas próprias, para `Extrude` e `Revolve`. |
| `Document` | `document.py` | Documento paramétrico: parâmetros + histórico de features + regeneração + exportação + relatório de propriedades de massa. |
| `generate_mesh` / `Mesh` | `mesher.py` | Geração de malha por Marching Cubes em blocos (float32, memória limitada), volume/área/centroide, exportação **STL binário** e **OBJ**, estatísticas em `mesh.stats`. Algoritmos alternativos implementam a interface `MeshGenerator`. |
| `show_mesh` | `viewer.py` | Visualizador 3D multiengine com sombreamento e escala real; salva PNG. |

## Exemplo mínimo

```python
from parametricus import Document, Box, Cylinder

doc = Document("Placa furada")
P = doc.params
P.define("L", 60,        description="Lado da placa")
P.define("esp", "L*0.2", description="Espessura (20% do lado)")
P.define("furo", "L/4",  description="Diâmetro do furo")

doc.set_body(lambda P:
    Box((lambda: P["L"], lambda: P["L"], lambda: P["esp"]))
    - Cylinder(lambda: P["furo"] / 2, lambda: P["esp"] * 3)
)

doc.rebuild()
print(doc.report())
doc.export_stl("placa.stl", resolution=128)

P.set("L", 100)          # muda o parâmetro mestre...
doc.rebuild()            # ...espessura e furo acompanham
doc.export_stl("placa_grande.stl")
doc.show()               # visualizador 3D interativo
```

> **Dica:** use `lambda: P["nome"]` para vincular dimensões a parâmetros
> (avaliação preguiçosa — a geometria "puxa" o valor atual a cada rebuild).
> Valores numéricos fixos também são aceitos.

## Vocabulário de modelagem

**Primitivas** — `Sphere(r)`, `Box((dx,dy,dz))`, `Cylinder(r,h)`,
`Cone(r1,r2,h)`, `Torus(R,r)`, `Capsule(a,b,r)`

**Esboço → feature** — `Extrude(perfil, altura)`, `Revolve(perfil)`
com perfis `CircleProfile`, `RectProfile(w,h,corner_radius)`,
`PolygonProfile(vertices)`, `RegularPolygonProfile(n, R)`

**Booleanas** — operadores Python: `a | b` (união), `a & b` (interseção),
`a - b` (subtração)

**Filetes** — `a.fillet_union(b, raio)`, `a.fillet_difference(b, raio)`,
`solido.round(raio)`

**Transformações** — `.translate(v)`, `.rotate(eixo, graus)`, `.scale(f)`,
`.mirror(normal)`

**Padrões** — `.array_linear(n, passo)`, `.array_polar(n, eixo)`

**Engenharia** — `.shell(espessura)` (casca oca)

## Engines de visualização

`show_mesh(mesh, engine=...)` (e `doc.show(engine=...)`) aceita:

| Engine | Dependências | Observações |
|---|---|---|
| `pyside6` | `PySide6`, `PyOpenGL` | Engine própria em OpenGL 3.3 Core (shaders Phong). |
| `pyvista` | `pyvista[all]` (VTK) | Recursos completos de cena, porém pesada em memória. |
| `trimesh` | `trimesh[easy]`, `pyglet<2` | Visualização rápida via trimesh. |
| `matplotlib` | `matplotlib` | Descontinuada. |

As engines são carregadas de forma preguiçosa: só as dependências da
engine selecionada precisam estar instaladas.

## Exemplos incluídos

| Script | O que demonstra |
|---|---|
| `examples/exemplo_flange.py` | Flange industrial dirigida por 2 parâmetros mestres; furos em padrão polar; filete estrutural; regeneração DN80 → DN120. |
| `examples/exemplo_caneca.py` | Esboço → revolução; raio **calculado a partir do volume desejado** (350 → 500 ml); alça toroidal com união suave. |
| `examples/exemplo_porca.py` | Extrusão de hexágono − círculo; chanfros por interseção com cones; escala M10 → M16 com um parâmetro. |

Execute-os com `python examples/exemplo_<nome>.py`; cada um imprime o
relatório paramétrico, exporta STL e salva uma imagem PNG do modelo.

## Qualidade de malha

`resolution` controla o nº de amostras no maior eixo do modelo:

- **64** — rascunho rápido (pré-visualização)
- **96–128** — padrão (boa para impressão 3D)
- **192–256** — alta fidelidade (mais lento)

O volume é amostrado em blocos (chunks) e o campo escalar fica em
float32, então a memória cresce com `resolution³ × 4 bytes` apenas —
resoluções altas são viáveis sem materializar a grade de pontos inteira.
`generate_mesh(..., verbose=True)` (ou `mesh.stats`) mostra tempo de
amostragem/extração, voxels avaliados, triângulos e pico estimado de
memória. Para algoritmos de malha alternativos (ex.: octree adaptativa),
implemente `MeshGenerator` e passe em `generate_mesh(..., generator=...)`.

O relatório inclui volume, área de superfície, dimensões e centroide —
úteis para verificação de projeto e estimativa de massa
(massa = volume × densidade do material).

## Arquitetura (por que SDF?)

Kernels B-Rep (como os de CAD comerciais) representam sólidos por faces
e arestas explícitas; booleanas exigem interseção superfície-superfície,
fonte clássica de falhas numéricas. Aqui cada sólido é uma função
`f(p) → distância`; booleanas viram `min`/`max`, filetes viram blends
polinomiais e cascas viram `|f| − t/2`. O custo é a discretização final
(Marching Cubes), controlada pelo parâmetro `resolution`.

## Limitações conhecidas

- A saída é malha triangular (STL/OBJ), não B-Rep (STEP/IGES).
- Arestas vivas são levemente suavizadas pela resolução da grade —
  aumente `resolution` para peças pequenas com detalhes finos.
- `SmoothUnion`/`Scale` não uniformes podem distorcer o campo de
  distância; o mesher tolera, mas filetes extremos merecem inspeção.
