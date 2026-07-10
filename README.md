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
| `ParameterSet` | `parameters.py` | Parâmetros nomeados com **expressões** (`"L/2"`, `"max(a,b)*0.1"`), grafo de dependências, detecção de ciclos, reavaliação em cascata e **rastreamento de leituras** (base do rebuild seletivo). |
| `SDF` e subclasses | `sdf.py` | Árvore de construção (CSG): primitivas, booleanas, transformações e operações de engenharia. Dimensões podem ser *lambdas* ligadas aos parâmetros. Cada nó tem uma **assinatura estrutural** usada pelos caches. |
| `Profile` | `sketch.py` | Esboços 2D (círculo, retângulo, polígono, polígono regular) com booleanas próprias, para `Extrude` e `Revolve`. |
| `ConstrainedSketch` | `constraints.py` | **Esboço com restrições**: entidades 2D, restrições geométricas/dimensionais e solver de mínimos quadrados (Levenberg-Marquardt). Dimensões aceitam `lambda: P["x"]`. |
| `Document` | `document.py` | Documento paramétrico: parâmetros + **histórico de features encadeado e editável** (suppress/edit/reorder) + **rebuild seletivo com cache** + **malhagem preguiçosa** + **Undo/Redo** + material + exportação + relatório. |
| `generate_mesh` / `Mesh` | `mesher.py` | Marching Cubes em blocos (float32), volume/área/centroide, **tensor de inércia**, exportação **STL/OBJ/PLY**, estatísticas em `mesh.stats`. Algoritmos alternativos implementam `MeshGenerator`. |
| `measure` | `measure.py` | **Medições e inspeção**: distância ponto→sólido (exata via SDF), caixa envolvente, **seção plana** (contornos, área, perímetro) e `slice_field` (heatmap do campo). |
| `io` | `io.py` | `export_mesh`/`import_mesh` por extensão: exporta `.stl/.obj/.ply`, importa `.stl/.obj`. |
| `MATERIALS` | `materials.py` | Materiais (Steel, Aluminum, Titanium, ABS, PLA); `doc.material` habilita massa e momentos de inércia no relatório. |
| `show_mesh` | `viewer.py` | Visualizador 3D multiengine com sombreamento e escala real; salva PNG. |
| `logger` | `_log.py` | Logging padrão de biblioteca; `enable_console_logging("DEBUG")` mostra cache hits, poda e estatísticas. |

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
`Cone(r1,r2,h)`, `Torus(R,r)`, `Capsule(a,b,r)`, `HalfSpace(normal,offset)`

**Esboço → feature** — `Extrude(perfil, altura)`, `Revolve(perfil)`
com perfis `CircleProfile`, `RectProfile(w,h,corner_radius)`,
`PolygonProfile(vertices)`, `RegularPolygonProfile(n, R)` ou
`ConstrainedSketch().profile([...])` (esboço resolvido por restrições)

**Booleanas** — operadores Python: `a | b` (união), `a & b` (interseção),
`a - b` (subtração)

**Filetes** — `a.fillet_union(b, raio)`, `a.fillet_difference(b, raio)`,
`solido.round(raio)`

**Transformações** — `.translate(v)`, `.rotate(eixo, graus)`, `.scale(f)`,
`.mirror(normal)`

**Padrões** — `.array_linear(n, passo)`, `.array_polar(n, eixo)` — ambos
por repetição de domínio: o filho é avaliado no máximo 3× por ponto,
independentemente de `n`

**Engenharia** — `.shell(espessura)` (casca oca), `.cut(normal, offset)`
(vista em corte)

**Medições** — `distance_point(solido, p)`, `bounding_box(solido | malha)`,
`section(solido, origem, normal)` (área/perímetro/contornos),
`slice_field(...)` (campo 2D para heatmap), `angle(v1, v2)`

## Histórico encadeado, cache e Undo/Redo

```python
doc.add_feature("Base", lambda P: Box((lambda: P["L"], 40, 10)))
doc.add_feature("Furo", lambda P, prev: prev - Cylinder(lambda: P["d"]/2, 99))
doc.rebuild()             # corpo = resultado da última feature

P.set("d", 12)            # só "Furo" regenera; "Base" sai do cache
doc.rebuild()

doc.suppress("Furo")      # suprime sem remover (como em CADs comerciais)
doc.edit_feature("Furo", nova_fn)
doc.reorder_feature("Furo", 0)
doc.undo(); doc.redo()    # parâmetros e edições de histórico
```

- `build(P)` → feature independente (compatível com a versão anterior);
  `build(P, prev)` → feature **encadeada** (recebe o sólido acumulado).
- `set_body(...)` continua funcionando e tem precedência (compatibilidade).
- A malha é **preguiçosa** (`get_mesh(resolution)`) e fica em cache por
  `(resolução, assinatura)` — reconstruir sem mudanças geométricas, ou
  voltar um parâmetro ao valor anterior, reaproveita a malha.
- Feature com erro não derruba o rebuild: fica marcada `!` no relatório e
  o encadeamento segue com o sólido anterior.

## Esboço com restrições

```python
sk = ConstrainedSketch()
a, b = sk.point(0, 0), sk.point(30, 1)
c, d = sk.point(31, 11), sk.point(-1, 12)
ab, bc, cd, da = sk.line(a,b), sk.line(b,c), sk.line(c,d), sk.line(d,a)
sk.fix(a); sk.horizontal(ab); sk.perpendicular(ab, bc)
sk.parallel(ab, cd); sk.parallel(bc, da)
sk.length(ab, lambda: P["W"]); sk.length(bc, lambda: P["H"])
print(sk.dof_report())            # "... -> totalmente restrito"

corpo = Extrude(sk.profile([a, b, c, d]), 10)   # re-resolve a cada rebuild
```

Restrições: `fix`, `coincident`, `horizontal`, `vertical`, `parallel`,
`perpendicular`, `tangent`, `symmetric` e as dimensionais `distance`,
`length`, `angle`, `radius` (aceitam `lambda: P["x"]`). O solver é
Levenberg-Marquardt em NumPy puro; `dof()`/`dof_report()` diagnosticam
sub/sobre-restrição via posto do Jacobiano.

## Materiais e propriedades de massa

```python
from parametricus import MATERIALS
doc.material = MATERIALS["Aluminum"]     # Steel, Titanium, ABS, PLA...
props = doc.mass_properties()            # massa (g), inércia (g·mm²)
print(doc.report())                      # inclui a seção MATERIAL
```

O tensor de inércia é integrado exatamente sobre a malha fechada
(tetraedros origem-face), no referencial do centroide.

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
| `examples/exemplo_placa_v11.py` | **Tour pela v1.1**: histórico encadeado, rebuild seletivo, undo/redo, esboço com restrições, medições/seção, materiais e I/O `.stl/.obj/.ply`. |

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

- A saída é malha triangular (STL/OBJ/PLY), não B-Rep. STEP/IGES ficam
  para a Fase 4.1 do roadmap (exigem OCCT como dependência opcional);
  a importação atual (`.stl`/`.obj`) devolve `Mesh` para medição e
  reexportação — booleanas com malhas importadas (`MeshSDF`) também são
  item futuro do roadmap.
- Arestas vivas são levemente suavizadas pela resolução da grade —
  aumente `resolution` para peças pequenas com detalhes finos.
- `SmoothUnion`/`Scale` não uniformes podem distorcer o campo de
  distância; o mesher tolera, mas filetes extremos merecem inspeção
  (dica: `slice_field` mostra o campo num plano).
- O Undo/Redo cobre parâmetros e edições de histórico; não coalesce
  mudanças contínuas (ex.: slider de GUI) — previsto junto com a GUI.

## Contribuidores

<a href="https://github.com/Manolo789/parametricus/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Manolo789/parametricus" />
</a>
