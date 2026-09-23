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

Escreva um `docs/instructions.md` (ou `.txt`) no seu projeto e rode:

```text
/ftd-gen --input-file ./docs/instructions.md --output json,md,html
```

Depois, se quiser:

```text
/ftd-chaos --run <run> --input-file ./docs/instructions.md --output json,md,html
/ftd-azure --run <run> --output json
```

- `--output` aceita `json`, `md`/`markdown` e `html`, sem diferenciar maiúsculas e minúsculas. O padrão é `json,md,html`. Também há `--diagnostics`, `--output-dir` e `--locale`.
- O arquivo de instruções diz o que ler, em que ordem e com que foco. As seções são livres: renomeie, remova ou crie as que quiser. O modelo as interpreta semanticamente, como orientação e sementes, nunca como autoridade. Veja o modelo em `docs/instructions.md`.
- O que você passa na linha de comando ou diz na conversa vale mais que o arquivo, e o arquivo vale mais que os padrões da skill.
- Pedidos em linguagem natural continuam funcionando: "gere os casos absurdos", "prepare isso para o Azure". O modelo entende a intenção no contexto; o Python só valida o alias exato e despacha.
- `/ftd-clarify`, `/ftd-check` e `/ftd-render` continuam disponíveis.
- `ftd-challenge` virou `/ftd-chaos`, e `ftd-mcp` virou `/ftd-azure`. Os nomes antigos só mostram uma mensagem de migração.

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

Por padrão, antes do design, cada fonte elegível é lida por um agente leve próprio: Haiku no Claude, com concorrência limitada. Cada leitor devolve só um catálogo factual, que o runtime valida e reconcilia; conflitos são preservados, sem votação. O modelo principal faz toda a síntese semântica. Catálogos de fontes que não mudaram são reaproveitados entre execuções, e uma fonte alterada invalida só a própria entrada. O usuário pode pedir leitura sequencial, sem subagentes, ou um número fixo de workers. O `/ftd-gen` orquestra tudo isso. Por baixo, os passos são:

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

## `/ftd-chaos` (opcional, pós-suíte)

Depois de `finalize`, `/ftd-chaos` faz a passada de cenários reais, adversos, físicos, de campo e "absurdos" sobre a suíte congelada, sem nunca reescrevê-la.

- As ideias do arquivo de instruções viram sementes item a item (`instructions.md#seed-001`), sempre inspiração e nunca autoridade. O modelo vai além delas usando o contexto já salvo da execução.
- Buscas de evidência são pontuais (`challenge.py lookup`), sem reler o projeto.
- Os casos novos usam `CH-*`, nunca `TC-*`, e seguem `STARTED → SUBMITTED → FINALIZED`.
- A saída fica em `output/chaos/<id>/`: `chaos-cases.json`, `chaos-plan.md` e `chaos-plan.html`, com o Manual/Physical/Field Test Plan.

## `/ftd-azure` (JSON local para Azure DevOps)

`/ftd-azure --run <run> --output json` converte a suíte canônica e as execuções de chaos finalizadas em JSON local, organizado requisito a requisito.

- Cada grupo tem o título `RF001 — Título oficial`, e há um grupo `Unassigned` no fim.
- A saída fica em `output/azure/`: `azure-export-package.json` e `azure-preview.json`.
- As chaves são `canonical:TC-001` e `chaos:<id>:CH-001`. Um TC ligado a vários requisitos é um único work item com várias posições, nunca um clone.
- O comando nunca se conecta ao Azure DevOps.
- `scripts/azure_export.py` só agrega o estado da FTD. `scripts/integrations/azure_devops.py` continua sendo o único dono do mapeamento, das Suites, do diff e do transporte.

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
docs/instructions.md        modelo genérico do arquivo de instruções
references/                 method, stage-contracts, test-design, validation, workflow, output-contract
schemas/                    JSON Schema Draft 2020-12
scripts/common.py           utilidades, idioma, similaridade
scripts/sources.py          escopo, papéis, leitura, identificadores oficiais, ativos de teste
scripts/instructions.py     arquivo de instruções: resolução, texto, pedido normalizado, precedência
scripts/reading.py          leitores leves por fonte: plano, catálogos, reconciliação, reuso
scripts/design.py           validação do estágio design e baseline
scripts/expansion.py        validação da segunda passada e do desafio dos testes existentes
scripts/procedures.py       validação dos procedimentos, readiness e métricas
scripts/validation.py       gates, gap metrics e validator público
scripts/pipeline.py         runtime: start, submit, finalize, render, verify
scripts/render.py           Markdown, HTML offline e catálogo de expansão
scripts/workflow.py         comandos ftd-* (alias exato + resolved_intent do host) e CLI gen/chaos/azure
scripts/benchmark.py        packs, comparação com baseline, reconciliação
scripts/challenge.py        internos do /ftd-chaos (CH-*), sem tocar a suíte canônica
scripts/azure_export.py     /ftd-azure: agregação FTD (canônico + chaos) em JSON local
scripts/integrations/       único dono do mapeamento, Suites, diff e publicação no Azure DevOps
benchmarks/domains/         packs A–F: SaaS, logística, ERP, IoT, aeronáutica, API
examples/                   exemplo sintético (schema 1.2)
tests/                      testes de regressão
```

## Limites atuais

A skill não executa testes em navegador, não cria Shared Steps reais, não faz indexação global/RAG do repositório e não publica no Azure DevOps (o `/ftd-azure` só gera JSON local).

Veja `CHANGELOG.md`, `MIGRATION-v2.3.0.md` e `SIMPLIFICATION_REPORT.md`.

## License and Attribution

The MIT license and required copyright notice are preserved in `LICENSE`. Adaptation details remain in `ATTRIBUTION.md`.
