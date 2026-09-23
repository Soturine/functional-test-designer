# Functional Test Designer v2.3.0

Agent Skill para projetar Test Cases funcionais rastreáveis e executáveis a partir somente das fontes que o usuário selecionou, em qualquer domínio.

## Ideia central

```text
O LLM faz o raciocínio de QA.
O runtime protege os poucos invariantes que garantem qualidade.
```

O núcleo semântico é do modelo: entender requisitos, inferir o domínio do projeto, decompor comportamento, encontrar contradições, imaginar erros de operador e falhas, e escrever procedimentos. O runtime cuida de escopo, contabilidade das fontes, identificadores oficiais, ids, validação, estado canônico e publicação. Ele nunca inventa cenários e nunca decide significado de negócio.

A skill não conhece nenhum domínio. O mesmo método produz "pallet errado na posição de armazenagem" em logística, "componente errado na ordem de manutenção" em aeronáutica, "cliente errado na fatura" em um ERP e "conta errada" em um app móvel. O vocabulário vem sempre das fontes selecionadas.

## Uso

A interface principal é linguagem natural:

```text
Use este PDF, docs/user, apps e config, gere os Test Cases,
salve HTML/JSON/Markdown e habilite diagnostics.
```

```text
"Pergunte o que ainda está ambíguo e pode mudar o desenho dos testes."
"Audite se os TCs podem ser executados por alguém que não conhece o produto."
"Renderize a última execução somente em HTML."
"Prepare a suíte para Azure DevOps e mostre o preview antes de qualquer escrita."
```

Os atalhos `ftd-gen`, `ftd-clarify`, `ftd-check`, `ftd-render` e `ftd-mcp` continuam funcionando e passam pelo mesmo core (`scripts/workflow.py`). É possível selecionar vários arquivos e diretórios, informar uma ordem de leitura ("primeiro os requisitos, depois o código"), escolher formatos, habilitar diagnostics, reaproveitar clarificações anteriores e informar o destino exato dos artefatos.

## Como funciona

```text
start       (runtime)  scope lock → registro das fontes → identificadores e títulos oficiais → idioma → ativos de teste
design      (modelo)   domain model → requisitos → claims atômicos → TCs Acceptance atômicos → disposições
                       ── baseline normativo congelado ──
expansion   (modelo)   17 dimensões · padrões de erro de operador · superfícies de falha ·
                       desafio dos testes existentes · caracterização · jornadas E2E   (somente aditivo)
procedures  (modelo)   passos executáveis · fixtures semânticas · unknowns · adequação à automação
finalize    (runtime)  validação (8 gates) → estado canônico → HTML / JSON / Markdown → prova de publicação
```

Cada estágio do modelo é um JSON enviado ao runtime. Um estágio inválido é rejeitado com todos os problemas de uma vez e nada é gravado. Depois de cada estágio o runtime escreve um `work-order.json` dizendo o que o próximo precisa contabilizar.

Para um corpus novo ou não cacheado, `start` planeja por padrão uma tarefa de leitura/catalogação por fonte elegível (`reading-task-plan.json`), pensada para agentes leves em paralelo (Haiku, quando o host oferece), com concorrência limitada. O usuário pode pedir explicitamente sequencial, um número fixo de workers ou outro modelo (`--reading-strategy`, `--reading-model`, `--reading-concurrency`); o agente principal continua sendo o único a decidir domain model, claims, oracles e tudo posterior. Fontes com o mesmo digest em execuções anteriores sob a mesma raiz de artefatos são marcadas reaproveitáveis.

```bash
python scripts/pipeline.py start --workspace <raiz> \
    --source "docs/requisitos.pdf=FUNCTIONAL_AUTHORITY" \
    --source "apps=IMPLEMENTATION_EVIDENCE" --source "docs/user=TECHNICAL_CONTEXT" \
    --artifact-root <destino> --run-id <id> --formats HTML,JSON,MARKDOWN --diagnostics
python scripts/pipeline.py submit --run <run> --stage design --file design.json
python scripts/pipeline.py submit --run <run> --stage expansion --file expansion.json
python scripts/pipeline.py submit --run <run> --stage procedures --file procedures.json
python scripts/pipeline.py finalize --run <run>
python scripts/pipeline.py verify --run <run>
```

## Princípios

- **Escopo:** somente fontes selecionadas. Um diretório é recursivo apenas dentro dele. Imports, links e vizinhos não ampliam o escopo.
- **Papéis:** `FUNCTIONAL_AUTHORITY` define o que deve acontecer. `IMPLEMENTATION_EVIDENCE` mostra o que existe, `TECHNICAL_CONTEXT` mostra como chegar lá, e `TEST_ASSET` (testes existentes) é um conjunto de desafio, nunca autoridade.
- **Nada inventado:** oracle, rota, rótulo, campo, mensagem, credencial ou estado sem evidência vira Question ou unknown do procedimento. Divergência entre autoridade e implementação vira Finding.
- **Idioma:** todo texto humano sai no `output_locale` da execução (pedido explícito > idioma da autoridade > idioma do pedido). Símbolos de código, endpoints e ids ficam literais.
- **Títulos oficiais:** o título de um TC descreve o comportamento testado, nunca "REQ-A — cabeçalho". Os identificadores ficam em `source_identifiers` e aparecem como chips no card do HTML: `TC-001 Comportamento atômico [REQ-A] [POLICY-B] [FLOW-C]`.
- **Baseline normativo:** cada claim testável gera um TC Acceptance atômico, que é congelado antes da expansão. A expansão só adiciona, e cada identificador da autoridade termina coberto ou com disposição explícita.
- **Segunda passada obrigatória:** as 17 dimensões são avaliadas (`NEGATIVE`, `BOUNDARY`, `OPERATOR_ERROR`, `MISUSE`, `STATE_TRANSITION`, `DECISION_TABLE`, `CONCURRENCY`, `RACE_CONDITION`, `IDEMPOTENCY`, `INTEGRATION`, `RECOVERY`, `CHAOS`, `SECURITY`, `AUTHORIZATION`, `DATA_INTEGRITY`, `CROSS_REQUIREMENT`, `E2E`), com 14 padrões universais de erro de operador e 15 superfícies de falha. Cada item é interpretado nos termos do projeto ou marcado como não aplicável com motivo.
- **Cobertura semântica:** um cenário adversarial não é "coberto" por um TC de caminho feliz, e um intent copiado do alvo é rejeitado. Superfícies de falha independentes não se fundem em uma pergunta genérica.
- **Procedimentos depois do design:** o test design decide o que testar, e a geração de procedimentos só explica como executar. Procedimentos não criam, apagam, fundem nem mudam TCs. Cada um cita `evidence_refs` ou declara a lacuna de caminho.
- **Readiness honesto:** `READY` não exige dados literais. Fixtures semânticas (`OPERADOR_A`, `CONTA_B`) bastam. Unknowns materiais tornam o caso `NEEDS_REVIEW`/`BLOCKED`, e unknowns só de automação afetam apenas `automation_readiness`. Adequação à automação (`automation_suitability`) e prontidão para automação (`automation_readiness`) são perguntas diferentes.
- **"0 gaps" só quando é verdade:** as seis dimensões de `gap_metrics` precisam estar zeradas. Uma baseline histórica não carregada aparece como `NOT_APPLIED`, nunca `PASS`.

## Gates

| Gate | Protege |
| --- | --- |
| `SCOPE_VALID` | Somente fontes selecionadas; um registro por fonte física. |
| `SOURCE_COVERAGE_VALID` | Todo identificador da autoridade coberto ou com disposição. |
| `NORMATIVE_BASELINE_VALID` | Cada claim testável com TC Acceptance atômico; baseline intacto após a expansão. |
| `ADDITIVE_EXPANSION_VALID` | Dimensões, padrões, superfícies, ativos de teste e jornadas avaliados; cobertura semanticamente alinhada. |
| `PROCEDURE_QUALITY_VALID` | Procedimento executável e fundamentado para cada TC, no idioma da execução. |
| `EVIDENCE_AND_REFERENCE_VALID` | Referências dentro do escopo; Questions/Findings ligados aos TCs. |
| `PIPELINE_INTEGRITY_VALID` | Estágios em ordem, conferidos pelo manifest com cadeia de hashes. |
| `PUBLICATION_VALID` | Arquivos públicos validados pelos schemas e presos aos digests de publicação. |

## Saída

```text
<destino>/
|-- output/
|   |-- test-cases.json         índice: requisitos, claims, CPs, famílias, disposições, gaps, gates
|   |-- questions.json
|   |-- report.html             relatório offline, agrupado por Scenario Family
|   |-- test-cases/TC-XXX.json  fonte de verdade de cada TC
|   `-- test-cases-md/TC-XXX.md versão humana, com fluxo Mermaid
|-- diagnostics/                com --diagnostics: domain model, candidatos, checklists,
|                               jornadas, desafio dos testes existentes, run-metrics
`-- .ftd/runs/<run-id>/         estado privado: estágios, work orders, manifest
```

O JSON é a fonte de verdade, e Markdown e HTML são projeções do estado canônico. Renderizar não relê fontes nem refaz o test design. O schema público continua 2.2, com campos opcionais novos, e suítes 1.2 continuam validando e renderizando.

## Desafio pós-suíte (opcional)

Depois de `finalize`, `ftd-challenge` faz uma última passada adversarial/operacional/física sobre a suíte já congelada, sem nunca reescrevê-la:

```bash
python scripts/challenge.py start --run <run> --challenge-id campo-1 --seed qa-ideas.md --focus "erro de operador e dispositivos físicos"
python scripts/challenge.py submit --run <run> --challenge-id campo-1 --file challenge.json
python scripts/challenge.py finalize --run <run> --challenge-id campo-1
```

Cada arquivo de seed é inspiração, nunca autoridade, e é dividido em itens endereçáveis (`qa-ideas.md#seed-001`, um por bullet); cada item recebe uma disposição honesta, e o modelo pode (e deve) ir além deles usando os atores, regras e evidências que a suíte já estabeleceu. Para fundamentar um passo em evidência real, `challenge.py lookup` busca um trecho delimitado no snapshot de evidências já gravado da execução (nunca relendo o projeto); só uma busca real conta em `runtime_targeted_lookups`. Os novos casos usam o namespace `CH-*`, nunca `TC-*`, seguem o estado `STARTED → SUBMITTED → FINALIZED` (sem reescrita: um erro se corrige com um novo `challenge-id`) e nunca tocam `canonical-suite.json`. `finalize` produz o Manual/Physical/Field Test Plan (`challenge-plan.md`), que reúne os novos `CH-*` com os TCs canônicos manuais/físicos/bloqueados por referência.

## Exportação para Azure DevOps (`ftd-azure`)

`ftd-azure` projeta os TCs canônicos de uma execução finalizada, mais as execuções de desafio já finalizadas, em um pacote organizado requisito a requisito:

```bash
python scripts/azure_export.py prepare --run <run>
python scripts/azure_export.py preview --run <run> --project P --plan L --suite S
python scripts/azure_export.py publish --run <run> --approved
```

`scripts/azure_export.py` só agrega estado da FTD (execução + desafios finalizados, chaves de exportação, relação requisito↔caso); `scripts/integrations/azure_devops.py` continua sendo o único dono do mapeamento, da colocação em Suites, do diff create/update/unchanged/conflict e da publicação. Um caso `CH-017` nunca vira `TC-244`: só a chave de exportação (`challenge:<id>:CH-017`) o identifica como Test Case no Azure, e chaves distintas por execução evitam colisão entre desafios que reutilizem `CH-001`. `ftd-mcp` (só canônico, uma suíte) continua funcionando sem mudanças.

## Validar e testar

```bash
python -m pip install -r requirements.txt
python scripts/validation.py <destino>/output --manifest <destino>/.ftd/runs/<run-id>/run-manifest.json
python scripts/render.py examples/expected-output
python scripts/benchmark.py packs          # seis packs multi-domínio (A–F)
python -m unittest discover -s tests
```

## Estrutura do repositório

```text
SKILL.md                    workflow da skill
references/                 method, stage-contracts, test-design, validation, workflow, output-contract
schemas/                    JSON Schema Draft 2020-12
scripts/common.py           utilidades, idioma, similaridade
scripts/sources.py          escopo, papéis, leitura, identificadores oficiais, ativos de teste
scripts/design.py           validação do estágio design e baseline
scripts/expansion.py        validação da segunda passada e do desafio dos testes existentes
scripts/procedures.py       validação dos procedimentos, readiness e métricas
scripts/validation.py       gates, gap metrics e validator público
scripts/pipeline.py         runtime: start, submit, finalize, render, verify
scripts/render.py           Markdown, HTML offline e catálogo de expansão
scripts/workflow.py         intents em linguagem natural e aliases ftd-*
scripts/benchmark.py        packs, comparação com baseline, reconciliação
scripts/challenge.py        desafio pós-suíte opcional (CH-*), sem tocar a suíte canônica
scripts/azure_export.py     agregação FTD (execução + desafios) para exportação ao Azure
scripts/integrations/       único dono do mapeamento, Suites, diff e publicação no Azure DevOps
benchmarks/domains/         packs A–F: SaaS, logística, ERP, IoT, aeronáutica, API
examples/                   exemplo sintético (schema 1.2)
tests/                      testes de regressão
```

## Limites atuais

A skill não executa testes em navegador, não cria Shared Steps reais, não faz indexação global/RAG do repositório e não escreve em Test Management sem preview e aprovação explícita.

Veja `CHANGELOG.md`, `MIGRATION-v2.3.0.md` e `SIMPLIFICATION_REPORT.md`.

## License and Attribution

The MIT license and required copyright notice are preserved in `LICENSE`. Adaptation details remain in `ATTRIBUTION.md`.
