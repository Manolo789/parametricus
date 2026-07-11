> **STATUS DA IMPLEMENTAÇÃO (v1.1.1, 2026-07-10)**
> ✅ Entregue: Fases 1, 2 e 3 integrais; Fase 4 quase integral (PLY/GLB/3MF,
> export por extensão, importação STL/OBJ, **MeshSDF** para booleanas com
> malhas importadas); Materiais e **biblioteca de componentes** (porca,
> arruela, parafuso, rosca helicoidal); `distance_solids` (distância mínima
> entre sólidos); coalescência e limite do Undo; config do `mypy`.
> ⏳ Pendente (exige dependências opcionais pesadas/ambiente gráfico):
> STEP/IGES (agora via núcleo-K, sem OCCT), GUI completa, rebuild assíncrono, clipping no shader do
> viewport PySide6, type hints completos do `viewer_backend`, entidade `Arc`
> nos sketch constraints, cache de campo escalar por nó SDF.
> Detalhes em CHANGELOG.md; validação em tests/test_roadmap.py (71 asserções).


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

- [ ] Retornos e parâmetros em todos os métodos dos backends de visualização (`viewer_backend/engine_pyside6/` é a área mais defasada).
- [ ] `np.ndarray` genérico → `numpy.typing.NDArray[np.float64]` / `NDArray[np.float32]` nos módulos numéricos (`sdf.py`, `sketch.py`, `mesher.py`), documentando shapes em docstrings (`(N, 3)`, `(V, 3)` já aparecem — padronizar).
- [X] Os aliases `Scalar` e `Vec3` estão duplicados em `sdf.py` e `sketch.py` → extrair para um `parametricus/types.py` único.
- [X] Adicionar `mypy` (ou `pyright`) ao fluxo com configuração gradual (`ignore_missing_imports` para skimage/PySide6). *(v1.1.1: `pyproject.toml` com `[tool.mypy]` gradual; `viewer_backend` sob `ignore_errors` até ser tipado.)*

**Esforço:** baixo. **Risco:** nenhum.

### 1.2 Logging em substituição a `print`

Há 8 chamadas a `print()` no núcleo (em `document.py`, `mesher.py` e viewers). Plano:

- [X] Criar `parametricus/_log.py` com `logging.getLogger("parametricus")` e um `NullHandler` (padrão de biblioteca — quem consome decide o handler).
- [X] `document.rebuild(verbose=True)` → manter o parâmetro por compatibilidade, mas mapear para `logger.info(...)`; `verbose=False` → `logger.debug(...)`.
- [X] Estatísticas do mesher (`MeshStats.report()`) permanecem como método de string; apenas a emissão vira log. *(v1.1.1: os 4 `print` restantes dos viewers também viraram `logger.info`.)*
- [X] Níveis: `DEBUG` = amostragem por chunk, poda; `INFO` = rebuild/export concluídos; `WARNING` = malha aberta, bbox degenerada.

**Esforço:** baixo. **Risco:** nenhum.

### 1.3 Cache inteligente (rebuild apenas da subárvore afetada) *(prioridade alta)*

Hoje o fluxo é: `ParameterSet.set()` → `on_change` → `Document._mark_dirty()` → `rebuild()` reconstrói **tudo** (todas as features + corpo + malha completa). A infraestrutura necessária já existe pela metade:

- [X] `ParameterSet` já mantém `depends_on` por parâmetro e reavaliação em cascata — ou seja, **já sabe quais parâmetros mudaram**. Falta propagar *quais* mudaram no callback: alterar `on_change(fn)` para `on_change(fn: Callable[[set[str]], None])` passando o conjunto de nomes afetados (o parâmetro alterado + fecho transitivo dos dependentes).
- [X] Do lado da geometria, o obstáculo é que as dimensões são `lambda: P["x"]` — opacas. *(Implementada a abordagem 1, rastreamento por leitura: `ParameterSet.tracking()`.)* Duas abordagens, em ordem de preferência:
  1. **Rastreamento por leitura (recomendado):** durante `rebuild`, `ParameterSet.__getitem__` registra os nomes lidos por cada nó/feature em avaliação (context manager `tracking(feature_id)`). Constrói-se automaticamente o mapa `parâmetro → nós SDF que o leem`, sem mudar a API do usuário.
  2. **Vinculação explícita:** substituir lambdas por um objeto `P.ref("x")` que carrega o nome. Mais limpo, porém quebra a API documentada no README.
- [X] Com o mapa em mãos: cada nó `SDF` ganha um `content_hash()` *(implementado como `SDF.signature()`)* (tipo + valores resolvidos + hashes dos filhos). No rebuild, nós cujo hash não mudou reutilizam o resultado anterior; apenas a subárvore afetada é reavaliada.
- [ ] *(parcial)* **Cache do campo escalar:** *(hoje: cache de MALHA por assinatura no `Document` e cache de sólidos por feature; o cache do campo float32 por nó SDF permanece como otimização futura)* o ganho real está no mesher. Guardar por nó (nos nós caros: `Revolve`, `PolygonProfile` extrudado, booleanas profundas) o campo float32 amostrado na última grade. Se o hash do nó e a grade coincidem, o campo é reutilizado — a mudança de um parâmetro do furo não reavalia o SDF da flange inteira.

**Esforço:** alto (é a mudança estrutural mais importante). **Risco:** médio — exige testes de regressão comparando malha com/sem cache.

### 1.4 Lazy meshing *(prioridade alta)*

Parcialmente implementado: `_ensure_mesh()` já evita regerar quando nada mudou. O que falta:

- [X] `rebuild()` hoje **sempre** gera malha. Separar em `rebuild_tree()` (só a árvore SDF, milissegundos) e geração de malha sob demanda (`doc.mesh` vira propriedade preguiçosa ou `doc.get_mesh(resolution)`).
- [X] Resolução em dois níveis: malha de **preview** (ex.: 48³) para o viewport interativo e malha de **exportação** (128³+) gerada apenas em `export_*`. O `_mesh_resolution` atual já dá o gancho — falta o conceito de perfis de qualidade.
- [X] Invalidação seletiva: com o cache da Fase 1.3, mudar um parâmetro que não afeta a geometria (ex.: `description`) não deve invalidar a malha.

**Esforço:** baixo/médio. **Risco:** baixo.

---

## Fase 2 — Núcleo do CAD

### 2.1 Histórico de features editável *(prioridade alta)*

A classe `Feature` existe, mas é decorativa: `rebuild()` avalia `f.build(params)` e descarta — o corpo vem só de `_body_fn`. Transformar o histórico em estrutura de primeira classe:

- [X] **Encadeamento real:** cada feature recebe o sólido acumulado e retorna o novo — `build(P, prev: SDF | None) -> SDF`. O corpo final passa a ser o resultado da última feature; `set_body` vira açúcar para "feature única" (compatibilidade preservada).
- [X] **Operações de edição:** `doc.remove_feature(name)`, `doc.reorder(name, index)`, `doc.suppress(name)` (equivalente ao *suppress* de CADs comerciais), `doc.edit_feature(name, build)`. Todas marcam dirty **a partir daquela feature** — as anteriores vêm do cache (sinergia direta com 1.3).
- [X] **Metadados:** cada `Feature` guarda os parâmetros que consome (via rastreamento de 1.3), timestamp e estado (`ok`/`suppressed`/`error`). Erro em uma feature não derruba o rebuild inteiro: features seguintes usam o último sólido válido e o documento reporta o estado.
- [X] `report()` já lista o histórico — passa a mostrar estado e dependências.

**Esforço:** médio/alto. **Risco:** médio (mudança de semântica de `add_feature`; mitigar com modo de compatibilidade).

### 2.2 Undo/Redo *(prioridade média, mas encaixa aqui)*

Com o histórico editável, undo/redo sai quase de graça pelo padrão *Command*:

- [X] Toda mutação do documento (definir/alterar parâmetro, adicionar/remover/reordenar/suprimir feature) vira um comando com `do()`/`undo()` empilhado em `doc.history` (duas pilhas: undo e redo).
- [X] `ParameterSet.set()` já retorna implicitamente o estado anterior via `Parameter.value` — o comando `SetParam` guarda `(nome, expr_antiga, expr_nova)`.
- [X] Limite configurável de profundidade; comandos coalescíveis (arrastar um slider na futura GUI gera 1 entrada, não 200). *(v1.1.1: `doc.undo_limit` e coalescência por janela `doc.coalesce_window`.)*

**Esforço:** baixo/médio **depois** de 2.1. **Risco:** baixo.

### 2.3 Sketch constraints *(prioridade alta)*

Hoje `sketch.py` tem perfis rígidos (círculo, retângulo, polígono) — não há entidades geométricas soltas (pontos, linhas, arcos) para restringir. É a feature de maior escopo do roadmap. Plano incremental:

- [X] 1. **Novo modelo de esboço** *(`constraints.py`: `Point2D`, `Line2D`, `Circle2D`; entidade `Arc` ainda pendente)* (`parametricus/sketch2/` ou expansão de `sketch.py`): entidades `Point2D`, `Line`, `Arc`, `Circle2D` com graus de liberdade explícitos (um ponto = 2 DOF, círculo = 3, etc.).
- [X] 2. **Restrições como resíduos:** cada constraint vira uma (ou mais) equação `f(q) = 0` sobre o vetor de incógnitas `q`:
   - *Coincidência:* `p1 - p2 = 0` (2 eq.)
   - *Horizontal/Vertical:* `y1 - y2 = 0` / `x1 - x2 = 0` (1 eq.)
   - *Paralelismo:* `cross(d1, d2) = 0` (1 eq.)
   - *Perpendicularidade:* `dot(d1, d2) = 0` (1 eq.)
   - *Tangência:* `dist(centro, linha) - r = 0` (1 eq.)
   - *Simetria:* reflexo em relação a uma linha (2 eq.)
   - *Dimensional:* distância/ângulo/raio = parâmetro do `ParameterSet` — **é aqui que o solver se liga ao sistema paramétrico existente.**
- [X] 3. **Solver:** *(implementado Levenberg–Marquardt próprio, sem SciPy; diagnóstico de DOF por posto do Jacobiano em `dof()`/`dof_report()`)* mínimos quadrados não linear (Gauss-Newton/Levenberg-Marquardt) sobre os resíduos. Começar com `scipy.optimize.least_squares` (adicionar SciPy como dependência opcional) e Jacobiano numérico; otimizar depois. Diagnóstico de sub/sobre-restrição pelo posto do Jacobiano (informar DOF restantes, como CADs comerciais fazem).
- [X] 4. **Ponte para o SDF:** *(`ConstrainedSketch.profile()` re-resolve sob demanda)* o esboço resolvido gera um `PolygonProfile`/composição de perfis existente — `Extrude`/`Revolve` continuam funcionando sem alteração.

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

- [X] `distance(a, b)` — entre pontos, ponto→superfície (o SDF **é** a função distância: `solid.distance(p)` já responde isso de graça — vantagem da arquitetura), e mínima entre dois sólidos (otimização sobre os dois campos). *(v1.1.1: a parte "entre dois sólidos" estava faltando e foi implementada em `distance_solids`, com semente em grade + projeções alternadas pelo gradiente do SDF.)*
- [X] `angle(v1, v2)` / entre faces planares detectadas na malha. *(v1.1.1: adicionado `face_normal_at(mesh, p)` para medir ângulo entre faces.)*
- [X] `bounding_box(solid)` — `bounds()` já existe em todo nó; expor com dimensões formatadas e opção de bbox justa (refinada pela malha, já disponível em `Mesh.bounding_box`).
- [X] `section_properties(solid, plane)` — área e perímetro da seção (amostra o SDF no plano + marching squares do skimage, já dependência do projeto).
- [X] Integrar ao `Document.report()`.

**Esforço:** baixo/médio. **Risco:** baixo.

### 3.3 Cortes por plano, Slice e Section *(prioridade média/alta)*

Três recursos distintos com implementações que se apoiam no que já existe:

- [X] **Section (curva 2D):** amostrar o SDF numa grade 2D sobre o plano de corte + `skimage.measure.find_contours` → polilinhas da seção. Nenhuma dependência nova.
- [X] **Slice (visualização do campo):** heatmap do SDF no plano — trivial e ótimo para depurar filetes/shells; cabe no backend matplotlib existente.
- [X] *(parcial)* **Corte no viewport 3D:** duas rotas *(a rota geométrica `HalfSpace`/`cut()` está implementada; o clipping no shader PySide6 permanece pendente)*:
  - *Geométrica:* `solid & HalfSpace(normal, offset)` — exige apenas um novo nó primitivo `HalfSpace` em `sdf.py` (≈15 linhas) e remesh. Funciona em qualquer backend.
  - *Visual (sem remesh):* clipping plane no shader do engine PySide6 (`discard` no fragment shader `phong.frag` + uniform do plano). Interativo e instantâneo; combinar com lazy meshing para a versão geométrica sob demanda.

### 3.4 Melhorias no viewport

- [ ] Plano de corte interativo (3.3), exibição das medições (3.2), gizmo de eixos, grid de chão com escala.
- [ ] Modos de exibição: sombreado / wireframe / arestas realçadas (arestas por ângulo diedro na malha).
- [ ] Regeneração assíncrona: rebuild + meshing em thread para não travar a UI do PySide6 (pré-requisito prático para a GUI de longo prazo).

**Esforço 3.3+3.4:** médio. **Risco:** baixo.

---

## Fase 4 — Interoperabilidade (prioridade baixa)

### 4.1 Importação: STL, OBJ, STEP

- [X] **STL/OBJ (fácil):** *(v1.1.1: nó `MeshSDF` implementado sem dependências — distância exata ponto→triângulo pré-amostrada em grade + interpolação trilinear; sinal por paridade de raios; kNN via SciPy quando disponível)* parsers próprios (STL binário é o espelho do `save_stl` existente) ou `trimesh`, que já é backend opcional de visualização. Malha importada entra como novo nó `MeshSDF` — SDF por distância à malha (consulta por BVH; `trimesh.proximity` fornece pronto). Isso permite **booleanas entre peças importadas e geometria paramétrica**, um diferencial real da arquitetura SDF.
- [~] **STEP:** rota mudou — em vez de OCCT, o repositório agora contém o **núcleo-K** (`nucleok/`), kernel B-Rep próprio (só NumPy). Leitor STEP próprio já cobre o subconjunto analítico manifold (PLANE/CYL/CONE/SPHERE/TORUS/REVOLUTION + LINE/CIRCLE/B-SPLINE); importar → `nucleok.tessellate` → `MeshSDF`. Falta: faces trimadas genéricas e assemblies.

### 4.2 Exportação: STEP, IGES, PLY, GLTF, 3MF

Em ordem de custo/benefício:

- [X] 1. **PLY** — formato trivial, mesmo padrão do `save_stl`/`save_obj` atuais; ~50 linhas.
- [X] 2. **GLTF/GLB** *(v1.1.1: escrita direta do GLB, sem dependências — `save_glb`/`doc.export("peca.glb")`)* — via `trimesh.export` (opcional) ou escrita direta do GLB (binário simples); útil para web/preview.
- [X] 3. **3MF** *(v1.1.1: ZIP + XML próprios — `save_3mf`/`doc.export("peca.3mf")`)* — ZIP + XML; escrita própria viável, relevante para impressão 3D.
- [~] 4. **STEP/IGES** — rota sem OCCT: o **núcleo-K** escreve STEP AP214 (MANIFOLD_SOLID_BREP) e IGES wireframe com código próprio. Sólidos construídos no núcleo-K (primitivas/extrusão/revolução) exportam com geometria analítica EXATA e round-trip validado; para SDFs do parametricus a exportação continua sendo malha (conversão com perda documentada) até existir reconstrução de superfícies.

Estruturar tudo em `parametricus/io/` com registro por extensão (`doc.export("peca.step")` despacha pelo sufixo).

**Esforço:** STL/OBJ/PLY/GLTF baixo; STEP/IGES alto. **Risco:** dependência pesada (OCCT) — manter estritamente opcional.

---

## Longo prazo

- [X] **Biblioteca de componentes** *(v1.1.1: `parametricus/library.py` — `nut()`, `washer()`, `hex_bolt()`, `nut_document()` com dimensões ISO M3–M12, e o nó helicoidal `HelicalThread` para roscas reais)* (parafusos, porcas, rolamentos, perfis, tubos): fábricas parametrizadas retornando `Document`/`SDF` prontos — o exemplo `exemplo_porca.py` já é o protótipo de uma `Nut(M8)`. Depende de: histórico de features (2.1) para componentes editáveis e, para roscas reais, de um nó helicoidal em `sdf.py` (SDF de hélice é bem conhecido na literatura de shaders).
- [X] **Sistema de materiais** (Steel, ABS, Aluminum, PLA, Titanium): `Material(nome, densidade, cor)` associado ao `Document`; massa = `mesh.volume() × ρ` (volume e centroide **já existem** em `mesher.py` — só falta o momento de inércia, que é a mesma integral por tetraedros do centroide, estendida aos termos de segunda ordem). Item de esforço surpreendentemente baixo; pode ser antecipado.
- [ ] **GUI completa** (árvore do documento, editor de parâmetros, histórico, viewport, console Python, inspetor, toolbar): o engine PySide6 existente é a base do viewport. Pré-requisitos reais: 1.3/1.4 (interatividade), 2.1/2.2 (árvore e undo), 3.4 (rebuild assíncrono). Sem eles, a GUI travaria a cada edição — por isso a GUI fecha o roadmap em vez de abri-lo.

---

## Sequência recomendada (resumo executivo)

1. **Type hints + logging** — 1 sprint, destrava tudo com segurança.
2. **Lazy meshing** — rápido, ganho imediato de interatividade.
3. **Cache inteligente** — a maior alavanca de desempenho; habilita 2.1.
4. **Histórico de features editável → Undo/Redo** — nesta ordem, o segundo é quase gratuito.
5. **Vetorização (PolygonProfile primeiro)** — hot loop mais visível nos exemplos atuais.
6. **Medições + Slice/Section + viewport** — valor de inspeção com baixo risco.
7. **Sketch constraints** — subprojeto em paralelo a partir do passo 4 (entidades → solver → integração com `ParameterSet`).
8. **I/O** — PLY/GLTF/STL-import cedo se houver demanda; STEP/IGES via **núcleo-K** (kernel próprio, sem OCCT) — ver `nucleok/README.md`.
9. **Materiais** (antecipável), **biblioteca de componentes** e **GUI** fecham o ciclo.
