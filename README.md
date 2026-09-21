# Functional Test Designer v2.2.0

Agent Skill para projetar Test Cases funcionais manuais, rastreáveis e executáveis a partir somente das fontes explicitamente selecionadas pelo usuário.

## Objetivo

Transformar requisitos, documentação, código selecionado e artefatos de QA em Test Cases independentes com passos claros, `Action + Expected Result`, rastreabilidade e cobertura comportamental verificável.

A skill foi feita para ser simples de usar: o usuário informa o que quer analisar e quais fontes entram no escopo; a skill cuida do restante.

Autoridade funcional define o comportamento obrigatório. Outras evidências explicitamente selecionadas podem enriquecer caminhos de execução, dados, observabilidade e desenho de cenários sem se tornarem verdade normativa. Um TC pode conter vários steps ordenados quando um único cenário independente exige uma sequência para alcançar o resultado.

Claims e Coverage Points permanecem atômicos, enquanto um TC representa uma execução independentemente repetível. Várias assertions observáveis da mesma execução podem compartilhar um TC; triggers, inputs, estados, branches, permissões ou plataformas independentes continuam separados. Vários steps pertencem ao mesmo TC somente quando formam um fluxo sequencial e os passos posteriores dependem do estado produzido pelos anteriores. O output nunca usa subtests.

```text
confirmar uma operação uma vez
→ verificar estado
→ verificar saldo
→ verificar auditoria
= 1 TC com múltiplas assertions

finalizar / reverter / cancelar
= 3 execuções independentes
= 3 TCs
```

## Como funciona

```text
Fontes selecionadas pelo usuário
            ↓
        Scope Lock
            ↓
Coleta/análise de evidência
(paralela quando seguro,
 ordenada quando solicitado)
            ↓
       Evidence Barrier
            ↓
  Autoridade semântica central
            ↓
 Atomic Claims → Clauses → CPs
            ↓
 Oportunidades em evidências selecionadas
            ↓
      Scenario Families
            ↓
     Test Cases → Freeze
            ↓
 Enriquecimento procedural
            ↓
 Estado canônico privado
            ↓
 JSON / Markdown / HTML offline
```

Uma pasta selecionada pode ser analisada recursivamente apenas dentro dela. Imports, links, dependências, arquivos vizinhos e outras áreas do projeto não expandem o escopo automaticamente.

## Confiança, autoridade e segurança

- somente fontes explicitamente selecionadas são analisadas;
- a skill não faz crawl automático do repositório nem segue dependências fora do escopo;
- requisitos e especificações aprovadas representam o comportamento esperado;
- código selecionado é tratado como evidência da implementação observada, não como autoridade funcional automática;
- divergência entre requisito e implementação vira finding, não um novo requisito silencioso;
- comportamento sem oracle suficiente vira Question ou permanece visivelmente bloqueado;
- Expected Results não devem ser inventados;
- JSON é a fonte de verdade dos Test Cases; Markdown e HTML são projeções derivadas;
- outputs e diagnósticos reais ficam fora do versionamento por padrão.

```text
LLM pode interpretar evidências.
LLM não deve inventar autoridade.
```

## Uso

A interface principal é linguagem natural. Os atalhos `ftd-gen`, `ftd-clarify`,
`ftd-check`, `ftd-render` e `ftd-mcp` são opcionais e usam exatamente o mesmo
core, as mesmas regras de autoridade e o mesmo estado canônico.

```text
"Gere Test Cases destas fontes e entregue somente HTML."
"Pergunte o que ainda está ambíguo e pode mudar o desenho dos testes."
"Audite se os TCs podem ser executados por alguém que não conhece o produto."
"Renderize a última execução em JSON e Markdown."
"Prepare a suíte para Azure DevOps e mostre o preview antes de qualquer escrita."
```

Em hosts que suportam comandos, as formas `/ftd-gen` ou `$ftd-gen` são apenas
aliases ergonômicos. Não é necessário memorizar comandos.

Exemplo simples:

```text
Use a functional-test-designer para gerar os Test Cases de:

docs/requirements.pdf

Diagnostic: true.
```

Exemplo com documentação e código selecionado:

```text
Use a functional-test-designer.

Analise somente:
- docs;
- dentro de src, somente orders.

Gere os Test Cases e aponte possíveis divergências.
Diagnostic: true.
```

A skill pode analisar, quando explicitamente selecionados, requisitos, especificações, documentação funcional/técnica, código-fonte, configuração, Test Cases existentes, planos de teste e outros artefatos relevantes à tarefa.

Quando várias fontes são selecionadas, a skill pode analisá-las em paralelo quando não existe dependência entre elas. Se o usuário informar uma ordem no pedido ou em um arquivo de instruções, essa ordem é respeitada. Fontes colocadas juntas continuam podendo ser processadas simultaneamente; etapas explicitamente posteriores aguardam as anteriores. A ordem de leitura controla somente quando coletar evidência: ela não altera o papel nem a prioridade normativa de nenhuma fonte.

Sem ordem explícita:

```text
Use a functional-test-designer.

Analise somente:
- docs/requirements;
- src/orders;
- docs/operator.

Gere os Test Cases e aponte divergências.
```

Com ordem natural no pedido:

```text
Analise somente docs/requirements, src/orders e docs/operator.

Primeiro analise os requisitos.
Depois o código de orders.
Por último consulte a documentação do operador.
```

Grupos também podem ser descritos naturalmente:

```text
Primeiro analise PRD e ADR.
Depois analise o código.
Por último consulte manual e configuração.
```

Uma instrução também pode vir em arquivo:

```text
Use as fontes selecionadas para gerar os Test Cases.
Siga a ordem de análise descrita em analysis-order.txt.
```

Nesse caso, `analysis-order.txt` orienta o trabalho e não vira requisito funcional automaticamente. A ordem nunca adiciona uma fonte que não esteja no escopo selecionado.

## Saída

Os artefatos são salvos no destino exato informado pelo usuário ou, na ausência dele, em um workspace confiável. A pasta da skill e o projeto analisado nunca são usados automaticamente como destino, e nenhuma pasta extra chamada `functional-test-designer` é acrescentada ao caminho escolhido.

```text
output/
|-- test-cases.json
|-- questions.json
|-- report.html
|-- test-cases/
|   |-- TC-001.json
|   |-- TC-002.json
|   `-- ...
`-- test-cases-md/
    |-- TC-001.md
    |-- TC-002.md
    `-- ...
```

A saída é organizada para servir tanto ao agente quanto a uma pessoa executando ou revisando os testes:

- `test-cases.json`: índice consolidado com requisitos, Coverage Points, cenários, rastreabilidade e referências para cada TC;
- `questions.json`: dúvidas e lacunas que precisam de confirmação antes de assumir um comportamento como verdade;
- `test-cases/TC-XXX.json`: fonte estruturada de cada Test Case, com objetivo, prioridade, preconditions, dados, steps, Expected Results, rastreabilidade, postconditions e cleanup;
- `test-cases-md/TC-XXX.md`: versão humana do mesmo TC, incluindo tabela de passos e fluxo Mermaid no final;
- `report.html`: visão agregada offline para revisar os TCs, pesquisar, filtrar, consultar cobertura, visualizar o fluxo de cada caso e abrir o JSON ou Markdown individual correspondente.

Para cada caso existe uma relação direta:

```text
TC-001.json
↔
TC-001.md
↔
TC-001 no report.html
```

O JSON continua sendo a fonte de verdade. Markdown e HTML apenas apresentam o mesmo conteúdo de formas mais fáceis de revisar e executar.

Quando o usuário pede formatos específicos, apenas essas projeções públicas são
materializadas. A renderização parte do estado canônico privado da execução,
não relê fontes do projeto e não refaz Test Design. Um HTML isolado não contém
links para JSON ou Markdown que não foram publicados.

## Clarificação, auditoria e integração

A clarificação prioriza até cinco dúvidas de alto impacto e registra respostas
como `USER_CLARIFICATION`, sem fingir que vieram das fontes originais. Conflitos
com autoridade aprovada permanecem visíveis.

A auditoria é read-only e pode focar procedimento, automação, coesão, cobertura
ou outputs. Readiness para automação significa que o caso pode ser traduzido de
forma determinística; não significa execução de navegador nesta versão.

A integração inicial com Azure DevOps Test Plans é preview-first. Ela separa
criações, atualizações, itens inalterados, ignorados e conflitos; não cria
`NEEDS_REVIEW` por padrão, não deleta itens ausentes e exige aprovação explícita
antes de qualquer escrita. Sem MCP disponível, gera apenas um export determinístico
de preview e não afirma que houve publicação.

Quando `Diagnostic: true` é usado, métricas separadas são escritas em `diagnostics/`, com tempos, contagens, escopo analisado, releituras e overhead, sem copiar o conteúdo das fontes.

Antes da finalização, uma auditoria source-first por RF/RN procura claims normativos omitidos independentemente do mapeamento clause→CP; uma única recuperação passa novamente pelo pipeline completo. A análise Cross-RF apenas sinaliza sobreposição e possíveis duplicatas para revisão, sem mesclar ou remover TCs automaticamente.

Antes de raciocinar sobre conteúdo, cada fonte selecionada resolvida recebe exatamente uma disposição de inspeção explícita. Contabilizar uma fonte não é o mesmo que abri-la: um binário, um arquivo gerado ou uma repetição equivalente pode permanecer sem leitura, mas com motivo registrado. Uma fonte sem disposição interrompe a execução. Métricas de leitura, concorrência e tempo de raciocínio relatam o que foi realmente observado ou ficam explicitamente indisponíveis, nunca zero fabricado.

O inventário source-first é uma segunda leitura genuína: declara seu método, oculta as contagens finais de Scenario, TC e tamanho de suíte, e não pode ser derivado da lista primária de claims. Ele inventaria unidades estruturais antes de resumir, de modo que um título de requisito com N critérios de aceite não vira um único Claim por padrão; uma unidade sem comportamento registra o motivo.

Depois da cobertura normativa, as demais evidências selecionadas passam por uma auditoria de oportunidades. Branches observáveis, divergências, ativos de QA e fluxos contínuos Cross-RF/E2E recebem um destino explícito sem transformar código ou testes legados em autoridade. Uma divergência fica ligada à cobertura normativa, caracterização, Question, Finding ou justificativa não executável — nunca apenas como prosa desconectada.

Claims preservam efeitos e alternativas observáveis de forma atômica, inclusive regras RN/CU explicitamente aplicáveis e disponíveis no escopo. Cada CP testável passa por candidates independentes. Na versão 2.2, Scenario é uma família/contexto: organiza vários TCs sem comprimi-los. Setup, navegação ou evento compartilhado podem aparecer como sugestão de merge, mas a visão canônica continua atômica. Depois do freeze, Evidence Packs enriquecem somente preconditions, dados, caminho, Steps, provenance e observabilidade; o oracle de Acceptance continua pertencendo à autoridade normativa. Uma lacuna de procedimento permanece visível como Question/`NEEDS_REVIEW`, sem menus, botões ou endpoints inventados.

Cada TC 2.2 declara sua base (`ACCEPTANCE`, `CHARACTERIZATION`, `DERIVED`, `EXPLORATORY`, `REGRESSION` ou `E2E`), tipo primário, readiness e metadados de automação. Missing implementation, Finding ou Question não apagam um design testável: alteram a classificação/status e mantêm as referências recíprocas. Casos E2E compõem TCs atômicos explicitamente, em vez de esconder a cobertura somente nos steps.

Steps seguem a complexidade natural do caminho documentado: navegação, busca, seleção, trigger e observação permanecem ações operacionais separadas quando a sequência suportada exige isso, enquanto um comportamento de uma única ação pode continuar com um Step. O relatório offline permanece uma projeção determinística e leve do JSON validado.

Uma ação vaga não pode comprimir um caminho detalhado disponível nas fontes. Casos com lacuna material de superfície, aquisição de dados, trigger ou observação ficam `NEEDS_REVIEW`; `READY` indica que uma pessoa nova no produto consegue executar o procedimento no nível sustentado pelas evidências. Readiness de automação é mais estrita e não autoriza inventar seletores ou código de runner.

Ativos de teste selecionados são inventariados mecanicamente por análise estática, sem importar nem executar o código inspecionado, e cada comportamento descoberto recebe uma classificação explícita. Um teste técnico não vira Test Case funcional, e nenhum ativo de teste vira autoridade normativa sozinho.

Uma matriz de risco revisa como um operador, um dispositivo, uma integração, um processo concorrente ou o ambiente podem quebrar o fluxo documentado, mantendo apenas o que as evidências selecionadas sustentam. É uma revisão, não um TC por dimensão. Quando a evidência não define o comportamento esperado, o resultado é um candidato de caracterização com uma Question focada — nunca um oracle inventado. Fluxos principais, alternativos e de exceção são revisados separadamente para E2E; um TC E2E é uma execução contínua e independentemente repetível cujos checkpoints rastreiam pelo menos dois CPs atômicos. Cenários adversariais, de resiliência e E2E aceitos continuam sendo Test Cases normais, sem modelo de objeto paralelo.

Uma precondição que apenas nomeia um registro não explica como obtê-lo. Quando o setup é material, o caso declara uma estratégia de aquisição e uma regra concreta, e detalhes procedurais vindos de evidência técnica, manual ou de implementação mantêm sua proveniência. Ambas as lacunas impedem que um caso apareça como simplesmente `READY`.

`operational-scenarios.md` é uma projeção determinística e opcional do estado canônico: um catálogo de revisão que liga Test Cases já existentes, nunca um segundo modelo de TC. Um mesmo TC canônico pode aparecer na suíte por requisito e em suítes estáticas orientadas a risco no Azure DevOps sem ser clonado.

Subtests encontrados em artefatos legados são normalizados: condições independentes viram TCs e ações sequenciais dependentes viram steps. O output final nunca contém `subtests`.

## Validar e renderizar

```bash
python -m pip install -r requirements.txt
python scripts/validate_output.py output
python scripts/render_markdown.py output
python scripts/render_report.py output
```

O validator verifica o contrato JSON e as referências cruzadas. Os renderers não alteram o conteúdo normativo dos JSONs.

Para validar o exemplo sintético:

```bash
python scripts/validate_output.py examples/expected-output
python scripts/render_markdown.py examples/expected-output
python scripts/render_report.py examples/expected-output
python -m unittest discover -s tests -v
```

O E2E sintético completo também pode ser executado em um artifact root temporário:

```bash
python scripts/run_synthetic_e2e.py <artifact-root>
```

## Estrutura do repositório

```text
SKILL.md                       Workflow da Agent Skill
references/                    Contrato, test design e diagnóstico
schemas/                       JSON Schema Draft 2020-12
scripts/resolve_scope.py       Resolução do escopo selecionado
scripts/resolve_artifacts.py   Resolução segura do destino dos artefatos
scripts/validate_output.py     Validação JSON e cross-file
scripts/render_markdown.py     Markdown determinístico por TC
scripts/render_report.py       Relatório HTML offline
scripts/diagnostics.py         Diagnóstico opcional de execução
scripts/generation_orchestrator.py  Pipeline compartilhado e gates reais de geração
scripts/source_inventory.py       Universo de fontes e autoridade v2.2
scripts/quality_gates.py          Gates independentes de qualidade
scripts/benchmark_reconciliation.py  Reconciliação explicável sem meta de contagem
scripts/risk_expansion.py         Expansão de risco sustentada por evidência
scripts/source_accounting.py        Ledger das fontes selecionadas e revisão independente
scripts/test_asset_inventory.py     Inventário estático de ativos de teste selecionados
scripts/risk_coverage.py            Matriz de risco e revisão de fluxos para E2E
scripts/render_operational_scenarios.py  Catálogo operacional opcional
scripts/run_operational_benchmarks.py    Execução dos packs sintéticos de benchmark
scripts/scenario_opportunities.py   Auditoria de oportunidades selecionadas
scripts/scenario_independence.py  Candidate-first e freeze da identidade
scripts/procedural_execution.py   Síntese procedural pós-freeze
scripts/parallel_evidence.py      Coleta paralela e grupos ordenados
scripts/procedural_pipeline.py    Workers procedurais e feedback aditivo
benchmarks/operational-workflows/  Packs sintéticos realistas A-D
examples/                      Exemplo sintético multi-source
tests/                         Testes de escopo, contrato e renderização
```

## Limites atuais

A skill não executa testes em navegador, não cria Shared Steps reais, não faz
indexação global/RAG do repositório e não escreve em Test Management sem preview
e aprovação explícita. `ftd-run` fica reservado para uma versão futura. O estado
canônico continua independente do payload de qualquer integração.

## License and Attribution

The MIT license and required copyright notice are preserved in `LICENSE`. Adaptation details remain in `ATTRIBUTION.md`.
