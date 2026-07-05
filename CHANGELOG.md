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

