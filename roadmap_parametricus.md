> **STATUS DA IMPLEMENTAÇÃO (v1.1.0, 2026-07-05)**
> ✅ Entregue: Fases 1, 2 e 3 integrais; Fase 4 parcial (PLY, export por
> extensão, importação STL/OBJ); Materiais (antecipado do longo prazo).
> ⏳ Pendente (exige dependências opcionais/escopo maior): STEP/IGES/GLTF/3MF,
> MeshSDF, biblioteca de componentes, GUI, rebuild assíncrono, clipping no viewport.
> Detalhes em CHANGELOG.md; validação em tests/test_roadmap.py (52 asserções).

# Roadmap de Melhorias — Parametricus

Estruturação das melhorias de `Melhorias.txt`, organizadas pelas prioridades definidas e ancoradas na arquitetura atual do projeto (`parameters.py`, `sdf.py`, `sketch.py`, `document.py`, `mesher.py`, `viewer_backend/`).

---

## Visão geral

| Fase | Tema | Itens | Dependências |
|---|---|---|---|
| **1** | Fundação técnica | Type hints completos · Logging · Cache inteligente · Lazy meshing | — |
| **2** | Núcleo do CAD | Histórico de features editável · Undo/Redo · Sketch constraints | Fase 1 (cache) |
| **3** | Desempenho e inspeção | Vetorização NumPy · Medições · Cortes/Seções · Melhorias no viewport | Fase 1 (lazy meshing) |
| **4** | Interoperabilidade | Importação STL/OBJ/STEP · Exportação STEP/IGES/GLTF/3MF/PLY | Fase 3 (parcial) |
| **Longo prazo** | Plataforma | Biblioteca de componentes · Sistema de materiais · GUI completa | Fases 1–3 |

A ordem inverte parcialmente a lista original de propósito: **type hints e logging (prioridade média) vêm antes**, porque são baratos, não têm dependências e tornam as refatorações grandes (cache, histórico) muito mais seguras. Fazer o cache primeiro e tipar depois significa tipar código que acabou de ser reescrito duas vezes.

---

## Fase 1 — Fundação técnica

### 1.1 Type hints completos *(prioridade média, mas primeiro)*

O projeto já usa `from __future__ import annotations` e tem hints parciais. Falta:

- Retornos e parâmetros em todos os métodos dos backends de visualização (`viewer_backend/engine_pyside6/` é a área mais defasada).
- `np.ndarray` genérico → `numpy.typing.NDArray[np.float64]` / `NDArray[np.float32]` nos módulos numéricos (`sdf.py`, `sketch.py`, `mesher.py`), documentando shapes em docstrings (`(N, 3)`, `(V, 3)` já aparecem — padronizar).
- Os aliases `Scalar` e `Vec3` estão duplicados em `sdf.py` e `sketch.py` → extrair para um `parametricus/types.py` único.
- Adicionar `mypy` (ou `pyright`) ao fluxo com configuração gradual (`ignore_missing_imports` para skimage/PySide6).

**Esforço:** baixo. **Risco:** nenhum.

### 1.2 Logging em substituição a `print`

Há 8 chamadas a `print()` no núcleo (em `document.py`, `mesher.py` e viewers). Plano:

- Criar `parametricus/_log.py` com `logging.getLogger("parametricus")` e um `NullHandler` (padrão de biblioteca — quem consome decide o handler).
- `document.rebuild(verbose=True)` → manter o parâmetro por compatibilidade, mas mapear para `logger.info(...)`; `verbose=False` → `logger.debug(...)`.
- Estatísticas do mesher (`MeshStats.report()`) permanecem como método de string; apenas a emissão vira log.
- Níveis: `DEBUG` = amostragem por chunk, poda; `INFO` = rebuild/export concluídos; `WARNING` = malha aberta, bbox degenerada.

**Esforço:** baixo. **Risco:** nenhum.

### 1.3 Cache inteligente (rebuild apenas da subárvore afetada) *(prioridade alta)*

Hoje o fluxo é: `ParameterSet.set()` → `on_change` → `Document._mark_dirty()` → `rebuild()` reconstrói **tudo** (todas as features + corpo + malha completa). A infraestrutura necessária já existe pela metade:

- `ParameterSet` já mantém `depends_on` por parâmetro e reavaliação em cascata — ou seja, **já sabe quais parâmetros mudaram**. Falta propagar *quais* mudaram no callback: alterar `on_change(fn)` para `on_change(fn: Callable[[set[str]], None])` passando o conjunto de nomes afetados (o parâmetro alterado + fecho transitivo dos dependentes).
- Do lado da geometria, o obstáculo é que as dimensões são `lambda: P["x"]` — opacas. Duas abordagens, em ordem de preferência:
  1. **Rastreamento por leitura (recomendado):** durante `rebuild`, `ParameterSet.__getitem__` registra os nomes lidos por cada nó/feature em avaliação (context manager `tracking(feature_id)`). Constrói-se automaticamente o mapa `parâmetro → nós SDF que o leem`, sem mudar a API do usuário.
  2. **Vinculação explícita:** substituir lambdas por um objeto `P.ref("x")` que carrega o nome. Mais limpo, porém quebra a API documentada no README.
- Com o mapa em mãos: cada nó `SDF` ganha um `content_hash()` (tipo + valores resolvidos + hashes dos filhos). No rebuild, nós cujo hash não mudou reutilizam o resultado anterior; apenas a subárvore afetada é reavaliada.
- **Cache do campo escalar:** o ganho real está no mesher. Guardar por nó (nos nós caros: `Revolve`, `PolygonProfile` extrudado, booleanas profundas) o campo float32 amostrado na última grade. Se o hash do nó e a grade coincidem, o campo é reutilizado — a mudança de um parâmetro do furo não reavalia o SDF da flange inteira.

**Esforço:** alto (é a mudança estrutural mais importante). **Risco:** médio — exige testes de regressão comparando malha com/sem cache.

### 1.4 Lazy meshing *(prioridade alta)*

Parcialmente implementado: `_ensure_mesh()` já evita regerar quando nada mudou. O que falta:

- `rebuild()` hoje **sempre** gera malha. Separar em `rebuild_tree()` (só a árvore SDF, milissegundos) e geração de malha sob demanda (`doc.mesh` vira propriedade preguiçosa ou `doc.get_mesh(resolution)`).
- Resolução em dois níveis: malha de **preview** (ex.: 48³) para o viewport interativo e malha de **exportação** (128³+) gerada apenas em `export_*`. O `_mesh_resolution` atual já dá o gancho — falta o conceito de perfis de qualidade.
- Invalidação seletiva: com o cache da Fase 1.3, mudar um parâmetro que não afeta a geometria (ex.: `description`) não deve invalidar a malha.

**Esforço:** baixo/médio. **Risco:** baixo.

---

## Fase 2 — Núcleo do CAD

### 2.1 Histórico de features editável *(prioridade alta)*

A classe `Feature` existe, mas é decorativa: `rebuild()` avalia `f.build(params)` e descarta — o corpo vem só de `_body_fn`. Transformar o histórico em estrutura de primeira classe:

- **Encadeamento real:** cada feature recebe o sólido acumulado e retorna o novo — `build(P, prev: SDF | None) -> SDF`. O corpo final passa a ser o resultado da última feature; `set_body` vira açúcar para "feature única" (compatibilidade preservada).
- **Operações de edição:** `doc.remove_feature(name)`, `doc.reorder(name, index)`, `doc.suppress(name)` (equivalente ao *suppress* de CADs comerciais), `doc.edit_feature(name, build)`. Todas marcam dirty **a partir daquela feature** — as anteriores vêm do cache (sinergia direta com 1.3).
- **Metadados:** cada `Feature` guarda os parâmetros que consome (via rastreamento de 1.3), timestamp e estado (`ok`/`suppressed`/`error`). Erro em uma feature não derruba o rebuild inteiro: features seguintes usam o último sólido válido e o documento reporta o estado.
- `report()` já lista o histórico — passa a mostrar estado e dependências.

**Esforço:** médio/alto. **Risco:** médio (mudança de semântica de `add_feature`; mitigar com modo de compatibilidade).

### 2.2 Undo/Redo *(prioridade média, mas encaixa aqui)*

Com o histórico editável, undo/redo sai quase de graça pelo padrão *Command*:

- Toda mutação do documento (definir/alterar parâmetro, adicionar/remover/reordenar/suprimir feature) vira um comando com `do()`/`undo()` empilhado em `doc.history` (duas pilhas: undo e redo).
- `ParameterSet.set()` já retorna implicitamente o estado anterior via `Parameter.value` — o comando `SetParam` guarda `(nome, expr_antiga, expr_nova)`.
- Limite configurável de profundidade; comandos coalescíveis (arrastar um slider na futura GUI gera 1 entrada, não 200).

**Esforço:** baixo/médio **depois** de 2.1. **Risco:** baixo.

### 2.3 Sketch constraints *(prioridade alta)*

Hoje `sketch.py` tem perfis rígidos (círculo, retângulo, polígono) — não há entidades geométricas soltas (pontos, linhas, arcos) para restringir. É a feature de maior escopo do roadmap. Plano incremental:

1. **Novo modelo de esboço** (`parametricus/sketch2/` ou expansão de `sketch.py`): entidades `Point2D`, `Line`, `Arc`, `Circle2D` com graus de liberdade explícitos (um ponto = 2 DOF, círculo = 3, etc.).
2. **Restrições como resíduos:** cada constraint vira uma (ou mais) equação `f(q) = 0` sobre o vetor de incógnitas `q`:
   - *Coincidência:* `p1 - p2 = 0` (2 eq.)
   - *Horizontal/Vertical:* `y1 - y2 = 0` / `x1 - x2 = 0` (1 eq.)
   - *Paralelismo:* `cross(d1, d2) = 0` (1 eq.)
   - *Perpendicularidade:* `dot(d1, d2) = 0` (1 eq.)
   - *Tangência:* `dist(centro, linha) - r = 0` (1 eq.)
   - *Simetria:* reflexo em relação a uma linha (2 eq.)
   - *Dimensional:* distância/ângulo/raio = parâmetro do `ParameterSet` — **é aqui que o solver se liga ao sistema paramétrico existente.**
3. **Solver:** mínimos quadrados não linear (Gauss-Newton/Levenberg-Marquardt) sobre os resíduos. Começar com `scipy.optimize.least_squares` (adicionar SciPy como dependência opcional) e Jacobiano numérico; otimizar depois. Diagnóstico de sub/sobre-restrição pelo posto do Jacobiano (informar DOF restantes, como CADs comerciais fazem).
4. **Ponte para o SDF:** o esboço resolvido gera um `PolygonProfile`/composição de perfis existente — `Extrude`/`Revolve` continuam funcionando sem alteração.

**Esforço:** alto (dividir em: entidades → 4 constraints básicas → solver → constraints restantes → dimensionais). **Risco:** médio/alto — é praticamente um subprojeto; manter os perfis atuais como caminho simples paralelo.

---

## Fase 3 — Desempenho e inspeção

### 3.1 Vetorização NumPy em SDF e mesher *(prioridade média)*

O núcleo já é majoritariamente vetorizado (as `distance()` operam em lotes `(N, 3)`, o mesher amostra em chunks de 500k pontos). Os loops Python restantes, por custo:

| Local | Loop | Correção |
|---|---|---|
| `sketch.py` → `PolygonProfile.distance` | `for i in range(n)` sobre arestas — chamado para **cada chunk** de pontos | Vetorizar sobre arestas com broadcasting `(N, E)`: distâncias a todos os segmentos de uma vez + regra de cruzamento vetorizada. É o hot loop de qualquer peça com hexágono/polígono (porcas do exemplo). |
| `sdf.py` → `array_linear` / `array_polar` | União iterativa de `count` cópias → árvore com profundidade O(n) | Nó dedicado `LinearArray`/`PolarArray` que avalia por módulo do domínio (`mod` das coordenadas) — O(1) avaliações independente de `count`, e a árvore fica rasa. |
| `mesher.py` → `save_obj` | `for v in vertices` escrevendo linha a linha | `np.savetxt` ou construção de string em bloco — exportação de malhas grandes cai de segundos para frações. |
| `sdf.py` → `Revolve.distance` | Já vetorizado, mas recalcula `_verts()` do perfil por chunk | Com o cache 1.3, memorizar vértices resolvidos dentro de um mesmo rebuild. |

**Esforço:** médio. **Risco:** baixo (cada item tem teste de equivalência numérica trivial).

### 3.2 Ferramentas de medição *(prioridade média)*

Novo módulo `parametricus/measure.py`, operando sobre `Mesh` e/ou diretamente sobre o SDF:

- `distance(a, b)` — entre pontos, ponto→superfície (o SDF **é** a função distância: `solid.distance(p)` já responde isso de graça — vantagem da arquitetura), e mínima entre dois sólidos (otimização sobre os dois campos).
- `angle(v1, v2)` / entre faces planares detectadas na malha.
- `bounding_box(solid)` — `bounds()` já existe em todo nó; expor com dimensões formatadas e opção de bbox justa (refinada pela malha, já disponível em `Mesh.bounding_box`).
- `section_properties(solid, plane)` — área e perímetro da seção (amostra o SDF no plano + marching squares do skimage, já dependência do projeto).
- Integrar ao `Document.report()`.

**Esforço:** baixo/médio. **Risco:** baixo.

### 3.3 Cortes por plano, Slice e Section *(prioridade média/alta)*

Três recursos distintos com implementações que se apoiam no que já existe:

- **Section (curva 2D):** amostrar o SDF numa grade 2D sobre o plano de corte + `skimage.measure.find_contours` → polilinhas da seção. Nenhuma dependência nova.
- **Slice (visualização do campo):** heatmap do SDF no plano — trivial e ótimo para depurar filetes/shells; cabe no backend matplotlib existente.
- **Corte no viewport 3D:** duas rotas:
  - *Geométrica:* `solid & HalfSpace(normal, offset)` — exige apenas um novo nó primitivo `HalfSpace` em `sdf.py` (≈15 linhas) e remesh. Funciona em qualquer backend.
  - *Visual (sem remesh):* clipping plane no shader do engine PySide6 (`discard` no fragment shader `phong.frag` + uniform do plano). Interativo e instantâneo; combinar com lazy meshing para a versão geométrica sob demanda.

### 3.4 Melhorias no viewport

- Plano de corte interativo (3.3), exibição das medições (3.2), gizmo de eixos, grid de chão com escala.
- Modos de exibição: sombreado / wireframe / arestas realçadas (arestas por ângulo diedro na malha).
- Regeneração assíncrona: rebuild + meshing em thread para não travar a UI do PySide6 (pré-requisito prático para a GUI de longo prazo).

**Esforço 3.3+3.4:** médio. **Risco:** baixo.

---

## Fase 4 — Interoperabilidade (prioridade baixa)

### 4.1 Importação: STL, OBJ, STEP

- **STL/OBJ (fácil):** parsers próprios (STL binário é o espelho do `save_stl` existente) ou `trimesh`, que já é backend opcional de visualização. Malha importada entra como novo nó `MeshSDF` — SDF por distância à malha (consulta por BVH; `trimesh.proximity` fornece pronto). Isso permite **booleanas entre peças importadas e geometria paramétrica**, um diferencial real da arquitetura SDF.
- **STEP (difícil):** exige kernel B-rep — usar `pythonocc-core`/OCCT como dependência opcional (`pip install parametricus[step]`). Importar → tesselar via OCCT → `MeshSDF`.

### 4.2 Exportação: STEP, IGES, PLY, GLTF, 3MF

Em ordem de custo/benefício:

1. **PLY** — formato trivial, mesmo padrão do `save_stl`/`save_obj` atuais; ~50 linhas.
2. **GLTF/GLB** — via `trimesh.export` (opcional) ou escrita direta do GLB (binário simples); útil para web/preview.
3. **3MF** — ZIP + XML; escrita própria viável, relevante para impressão 3D.
4. **STEP/IGES** — o mais difícil: SDF→malha→B-rep é conversão com perda (superfícies viram facetas). Caminho realista: exportar a malha tesselada embrulhada em STEP via OCCT, documentando a limitação; reconstrução de superfícies analíticas fica fora de escopo.

Estruturar tudo em `parametricus/io/` com registro por extensão (`doc.export("peca.step")` despacha pelo sufixo).

**Esforço:** STL/OBJ/PLY/GLTF baixo; STEP/IGES alto. **Risco:** dependência pesada (OCCT) — manter estritamente opcional.

---

## Longo prazo

- **Biblioteca de componentes** (parafusos, porcas, rolamentos, perfis, tubos): fábricas parametrizadas retornando `Document`/`SDF` prontos — o exemplo `exemplo_porca.py` já é o protótipo de uma `Nut(M8)`. Depende de: histórico de features (2.1) para componentes editáveis e, para roscas reais, de um nó helicoidal em `sdf.py` (SDF de hélice é bem conhecido na literatura de shaders).
- **Sistema de materiais** (Steel, ABS, Aluminum, PLA, Titanium): `Material(nome, densidade, cor)` associado ao `Document`; massa = `mesh.volume() × ρ` (volume e centroide **já existem** em `mesher.py` — só falta o momento de inércia, que é a mesma integral por tetraedros do centroide, estendida aos termos de segunda ordem). Item de esforço surpreendentemente baixo; pode ser antecipado.
- **GUI completa** (árvore do documento, editor de parâmetros, histórico, viewport, console Python, inspetor, toolbar): o engine PySide6 existente é a base do viewport. Pré-requisitos reais: 1.3/1.4 (interatividade), 2.1/2.2 (árvore e undo), 3.4 (rebuild assíncrono). Sem eles, a GUI travaria a cada edição — por isso a GUI fecha o roadmap em vez de abri-lo.

---

## Sequência recomendada (resumo executivo)

1. **Type hints + logging** — 1 sprint, destrava tudo com segurança.
2. **Lazy meshing** — rápido, ganho imediato de interatividade.
3. **Cache inteligente** — a maior alavanca de desempenho; habilita 2.1.
4. **Histórico de features editável → Undo/Redo** — nesta ordem, o segundo é quase gratuito.
5. **Vetorização (PolygonProfile primeiro)** — hot loop mais visível nos exemplos atuais.
6. **Medições + Slice/Section + viewport** — valor de inspeção com baixo risco.
7. **Sketch constraints** — subprojeto em paralelo a partir do passo 4 (entidades → solver → integração com `ParameterSet`).
8. **I/O** — PLY/GLTF/STL-import cedo se houver demanda; STEP/IGES por último, atrás de flag opcional OCCT.
9. **Materiais** (antecipável), **biblioteca de componentes** e **GUI** fecham o ciclo.
