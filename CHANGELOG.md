CHANGELOG

[2026/07/11] — núcleo-K 0.1.0 (kernel B-Rep próprio, sem OCCT):

Novo pacote independente `nucleok/` (única dependência: NumPy; zero imports
do parametricus — verificado em teste). Kernel de geometria computacional
em 6 camadas:
-Camada 1 (core): tolerâncias centralizadas; Transform 4x4 (translação,
 Rodrigues, escala, espelho Householder, normais por inversa-transposta);
 predicados robustos orient2d/orient3d com filtro float64 e fallback EXATO
 em fractions.Fraction.
-Camada 2 (geom): Line/Circle/Ellipse/Polyline com comprimento por
 Gauss-Legendre; NURBS completas (Piegl & Tiller A2.1/A2.2/A2.3/A5.1,
 racionais; círculo exato de 9 pontos com desvio ~1e-16); superfícies
 Plane/Cylindrical/Conical/Spherical/Toroidal/Revolution com inversão
 paramétrica (parameters_of) e subdivisões por deflexão de corda.
-Camada 3 (topo): Vertex/Edge/Loop/Face/Shell/Solid com separação rigorosa
 geometria×topologia (aresta = recorte de curva ilimitada; face = recorte
 de superfície + same_sense; arestas compartilhadas entre faces).
-Camada 4 (algo): interseções (reta/plano/esfera/cilindro em forma
 fechada; curva×plano por bisseção+Newton; Möller-Trumbore); classificação
 ponto×sólido por paridade de raio; ear clipping com furos (pontes de
 Eberly, decisões por predicado exato); tesselação por grade paramétrica
 (patches) e recorte planar; operadores de Euler mvfs/mev/mef em half-edge
 (tetraedro V4/E6/F4 χ=2 no teste, volume exato 1/6); validação
 Euler-Poincaré + fechamento 2-manifold; volume/área/centroide por
 divergência.
-Camada 5 (model): make_box/make_cylinder/make_sphere/make_torus com
 topologias canônicas validadas (χ=2/2/2/0); extrude com furos (prisma
 com furo passante: χ=0, volume exato); revolve por RevolutionSurface
 (validado com Pappus); booleanas com API estabilizada e plano de
 implementação documentado (próximo marco).
-Camada 6 (io): STEP AP214 — escritor E leitor próprios
 (MANIFOLD_SOLID_BREP; PLANE/CYL/CONE/SPHERE/TORUS/SURFACE_OF_REVOLUTION;
 LINE/CIRCLE/B_SPLINE_CURVE_WITH_KNOTS; round-trip com topologia idêntica
 e Δvolume = 0 em caixa/cilindro/esfera/toro/revolução/extrusão-com-furo);
 STL binário/ASCII (escrita+leitura); IGES 5.3 wireframe (110/100/106).
-Suíte tests/test_nucleok.py: 53 asserções (todas passando) + as 71 da
 suíte v1.1.1 continuam verdes. Roadmap atualizado: rota STEP/IGES sai de
 "OCCT opcional" para "núcleo-K próprio".


[2026/07/10] — v1.1.1 (auditoria dos checkboxes do roadmap + itens pendentes):

Auditoria: os itens marcados [X] foram verificados contra o código e a suíte
(52 asserções, todas passando). Uma lacuna foi encontrada dentro de um item
marcado como feito (3.2: faltava a distância mínima ENTRE dois sólidos) e
corrigida. Checkboxes do roadmap sincronizados com a implementação real.

Novidades:
-measure.distance_solids(a, b): distância mínima entre dois sólidos —
 semente em grade grossa + projeções alternadas pelo gradiente dos SDFs;
 detecta interpenetração (d = 0). measure.face_normal_at(mesh, p) para
 medir ângulo entre faces planares da malha (complemento do item 3.2).
-Fase 4.2: exportação GLB (glTF 2.0 binário, escrita direta) e 3MF
 (ZIP + XML próprios), registradas no despacho por extensão:
 doc.export("peca.glb") / doc.export("peca.3mf").
-Fase 4.1: nó MeshSDF — malhas importadas (STL/OBJ) viram SDF e participam
 de booleanas com geometria paramétrica. Distância exata ponto→triângulo
 pré-amostrada em grade regular (kNN via SciPy quando disponível, força
 bruta em blocos caso contrário) + sinal por paridade de raios por linha
 da grade; consultas por interpolação trilinear.
-Fase 2.2 (conclusão): doc.undo_limit (profundidade da pilha) e
 coalescência de mudanças consecutivas do mesmo parâmetro dentro de
 doc.coalesce_window (arrastar um slider gera 1 entrada de undo).
-Longo prazo: biblioteca de componentes (parametricus/library.py) —
 nut(), washer(), hex_bolt(), nut_document() com dimensões ISO M3–M12 e
 nó HelicalThread (rosca métrica aproximada com reescala de Lipschitz).
-Fase 1.1 (conclusão parcial): pyproject.toml com configuração gradual do
 mypy (ignore_missing_imports para skimage/PySide6/SciPy; viewer_backend
 sob ignore_errors até ser tipado). Empacotamento PEP 621 com extras
 [viewer], [fast] (SciPy) e [dev].
-Fase 1.2 (conclusão): últimos 4 print() (backends de visualização)
 migrados para logger.info.

Pendências remanescentes (dependem de OCCT/ambiente gráfico): STEP/IGES,
GUI completa, rebuild assíncrono, clipping no shader do viewport, type
hints do viewer_backend, entidade Arc nos sketch constraints, cache de
campo escalar por nó SDF.

Suíte ampliada: tests/test_roadmap.py com 71 asserções, todas passando.

[2026/07/05 21:40] — v1.1.0 (implementação do roadmap, Fases 1-3 + itens da Fase 4):

Fase 1 — Fundação:
-Logging padrão de biblioteca (_log.py): logger "parametricus" com NullHandler;
 enable_console_logging()/disable_console_logging(); prints do mesher/document
 migrados para logger (DEBUG/INFO/WARNING).
-Aliases de tipos compartilhados (types.py): Scalar/Vec3/FloatArray e
 resolve_scalar/resolve_vec3, antes duplicados em sdf.py e sketch.py.
-Rastreamento de leituras no ParameterSet (tracking()), notificação com o
 conjunto de parâmetros efetivamente alterados (on_change(cb(changed))),
 dependents_of() transitivo e set() no-op quando a expressão não muda.
-Assinatura estrutural nos nós SDF/Profile (signature()): hash dos valores
 resolvidos (lambdas avaliadas), recursivo nos filhos — base dos caches.
-Rebuild seletivo no Document: cada feature registra os parâmetros lidos e
 só regenera se algum deles mudou (ou se uma feature anterior mudou).
-Malhagem preguiçosa: get_mesh(resolution) com cache (resolução, assinatura)
 e LRU — rebuilds sem mudança geométrica (inclusive voltar um parâmetro ao
 valor anterior) reutilizam a malha. preview_resolution/export_resolution.

Fase 2 — Núcleo:
-Histórico de features encadeado e editável: build(P, prev) recebe o sólido
 acumulado; corpo = última feature (set_body mantém precedência/compat).
 suppress/unsuppress, remove_feature, reorder_feature, edit_feature; estados
 ok/suppressed/error/stale no relatório; feature com erro não derruba o
 rebuild (segue com o sólido anterior + WARNING).
-Undo/Redo (padrão Command): mutações de parâmetro (via hook on_mutate do
 ParameterSet) e todas as edições de histórico; undo_labels para inspeção.
-Sketch constraints (constraints.py): Point2D/Line2D/Circle2D; restrições
 fix, coincident, horizontal, vertical, parallel, perpendicular, tangent,
 symmetric + dimensionais distance/length/angle/radius (aceitam
 lambda: P["x"]); solver Levenberg-Marquardt em NumPy puro; dof()/dof_report()
 por posto do Jacobiano; sketch.profile(loop) gera PolygonProfile que
 re-resolve quando os parâmetros mudam.

Fase 3 — Desempenho e inspeção:
-PolygonProfile.distance otimizado (2,2-2,7x): o loop original já era
 vetorizado sobre os pontos; o ganho veio de eliminar temporários 2D
 (componentes x/y separados, minimum in-place, paridade inteira de
 cruzamentos). Equivalência numérica validada por regressão.
-array_linear por repetição de domínio (nó LinearArray): filho avaliado no
 máximo 3x por ponto, independente de count (antes: cadeia de uniões O(n)).
-save_obj vetorizado (np.savetxt em blocos).
-Medições (measure.py): distance_point (exata via SDF), distance_points,
 angle, bounding_box (SDF ou Mesh, com report()).
-Seções e cortes: section() (contornos 2D/3D via marching squares, área e
 perímetro), slice_field() (campo no plano p/ heatmap), primitiva HalfSpace
 e atalho solido.cut(normal, offset).

Fase 4 — Interoperabilidade (itens sem dependências novas):
-Exportação PLY binário com normais (Mesh.save_ply).
-export_mesh/Document.export com despacho por extensão (.stl/.obj/.ply).
-Importação import_mesh/load_stl (binário e ASCII, com solda de vértices)
 e load_obj (triangulação em leque), com normais por vértice ponderadas
 por área. STEP/IGES/GLTF/MeshSDF permanecem no roadmap (exigem OCCT/trimesh).

Materiais (antecipado do longo prazo):
-materials.py: Material + MATERIALS (Steel, Aluminum, Titanium, ABS, PLA).
-Mesh.inertia_tensor(density): integração exata sobre tetraedros origem-face,
 no referencial do centroide; Mesh.mass_properties(); doc.material habilita
 massa e momentos principais no report(); doc.mass_properties().

Testes:
-tests/test_roadmap.py: 52 asserções cobrindo todas as fases (validações
 numéricas contra soluções analíticas: área/perímetro de seção, meia esfera,
 inércia de caixa, round-trips STL/OBJ).
-Exemplo novo examples/exemplo_placa_v11.py (tour pela v1.1).
-Compatibilidade retroativa verificada nos 3 exemplos originais.

CHANGELOG

[2026/07/05 00:36]:
Implementação de motores gráficos 3D adicionais:
-Matplotlib foi descontinuado
-PyVista definido como padrão
-Trimesh implementado
-Engine gráfica própria implementada com PySide6+OpenGL

[2026/07/04 19:10]:

-Criação do arquivo .gitignore

Bugs:
-Modificação na função rebuild() em document.py para corrigir o erro: ao atualizar a resolução, a árvore de features continuava com a resolução anterior. Para corrigir isso, foi adicionada a condição da resolução atual ser diferente de uma variável temporária.
-Normais de vértice invertidas no OBJ: Para corrigir, foi aplicado 'normals = -normals' em mesher.py. É necessário testar para verificar se isso afeta para STL.

Otimização:
-Alteração do arquivo mesher.py para melhor performace.

-Ateração de 'array\_polar' por repetição de domínio.
-Adição da função pruned\_margin em conjunto com a otimização em mesher.py. Tal função ficará em sdf.py

