# Functional Test Designer

Agent Skill que projeta **Test Cases funcionais rastreáveis e executáveis** a partir somente das fontes que você seleciona — requisitos, documentação, código e testes existentes —, em qualquer domínio.

- **Entra:** um arquivo `instructions.md` dizendo o que ler e onde focar.
- **Sai:** uma suíte de Test Cases em JSON (fonte de verdade), Markdown e um relatório HTML offline, com Questions, Findings, cobertura e rastreabilidade.
- **Opcional:** uma passada pós-suíte de cenários reais e adversos (`/ftd-chaos`), um pacote local para Azure DevOps (`/ftd-azure`) e, só se você pedir explicitamente, a publicação no Azure DevOps (`/ftd-azure-publish`).

O modelo faz o raciocínio de QA; o runtime protege escopo, rastreabilidade, validação e publicação. Nada é inventado: o que as fontes não dizem vira Question ou pendência.

> Versão publicada: 2.3.0. O branch `develop` prepara a 2.4 (ainda não lançada).

## Início rápido

1. Copie [`docs/instructions.md`](docs/instructions.md) para o seu projeto e edite as fontes.
2. Rode:

```text
/ftd-gen --input-file ./docs/instructions.md --output json,md,html --diagnostics --output-dir ./ftd-output
```

3. Abra `./ftd-output/output/report.html`.

`--output-dir ./ftd-output` significa "salve todos os artefatos da FTD em `./ftd-output`" (o padrão é `<workspace>/ftd-output`). Sem `--run-id`, a FTD cria um id como `ftd-20260925-143000`; o estado da execução fica em `./ftd-output/.ftd/runs/<run-id>/`.

Você normalmente não precisa copiar esse id: depois de uma geração bem-sucedida, a FTD lembra a **execução validada atual** (`./ftd-output/.ftd/current-run.json`), e os comandos seguintes a usam quando `--run` é omitido. Só uma execução canônica VALIDATED vira a atual — nunca uma execução que falhou, ficou incompleta ou um chaos —, e ela é conferida de novo a cada uso. Para uma execução mais antiga ou específica, passe `--run <run-id>`.

## O arquivo `instructions.md`

Um arquivo de configuração humano, não uma DSL. Os títulos são livres; o modelo interpreta o texto semanticamente.

```markdown
## Sources
1. `docs/requirements.pdf` — functional authority
2. `docs/user/` — product context
3. `src/` — implementation evidence
4. `tests/` — existing tests

Do not read anything else.

## Things I want you to explore
- wrong actor or resource
- interruption and recovery
```

- É orientação, nunca autoridade: uma ideia que as fontes não sustentam não vira Test Case normativo, e as ideias não limitam a análise.
- Cada ideia recebe uma resposta explícita (materializada, já coberta, usada para ordenar, Question ou não aplicável com motivo) — nunca some em silêncio.
- O que você diz na conversa ou passa na linha de comando vale mais que o arquivo.

Ações depois da run também podem ir no arquivo, com as palavras que você quiser:

```markdown
## Depois da run
- fazer chaos
- converter azure
```

A FTD entende o pedido pelo sentido (títulos e frases livres) e segue: suíte → chaos → relatório atualizado → pacote **local** do Azure → para. "Converter/gerar/preparar Azure" é sempre o pacote local; `/ftd-azure-publish` nunca roda sozinho. Na linha de comando, `--after chaos,azure` ou `--after none` substitui o arquivo.

Modelo completo e comentado: [`docs/instructions.md`](docs/instructions.md).

## Comandos

| Comando | O que faz | Escreve fora da máquina? |
| --- | --- | --- |
| `/ftd-gen` | Lê as fontes selecionadas e gera a suíte canônica | Não |
| `/ftd-chaos` | Opcional: casos pós-suíte reais, adversos, físicos e de campo (`CH-*`) sobre uma suíte finalizada | Não |
| `/ftd-render` | Re-renderiza a partir do estado salvo, sem reler fontes | Não |
| `/ftd-check` | Auditoria somente leitura da suíte | Não |
| `/ftd-clarify` | Lista as Questions mais importantes | Não |
| `/ftd-azure` | Gera o pacote **local** (JSON) para Azure DevOps | **Não — nunca se conecta** |
| `/ftd-azure-publish --prepare` | Lê o destino no Azure DevOps e gera um plano local | Não (só leitura remota) |
| `/ftd-azure-publish --apply` | Publica o plano revisado | **Sim — só após aprovação explícita** |

Pedidos em linguagem natural também funcionam ("rode o chaos", "gere o pacote do Azure"). "Gerar/converter/preparar Azure" significa sempre o pacote local; publicar exige pedido explícito.

## Fluxo completo

```text
/ftd-gen   --input-file ./docs/instructions.md --output json,md,html --output-dir ./ftd-output
/ftd-chaos --input-file ./docs/instructions.md --output json,md,html
/ftd-azure
```

Para uma execução específica: `/ftd-azure --run <run-id>` (vale para `/ftd-chaos`, `/ftd-check`, `/ftd-render` e `/ftd-azure-publish --prepare`). Se o artefato estiver em outra pasta, use `--output-dir`.

- `/ftd-chaos` nunca altera a suíte canônica; ao finalizar, o relatório, a organização e o plano de execução são atualizados para mostrar os casos `CH-*`.
- `/ftd-azure` escreve `output/azure/azure-export-package.json` e `azure-preview.json`: um work item por caso, várias Suites por caso quando preciso, nunca clones.

### Publicar no Azure DevOps (opcional, explícito)

```text
/ftd-azure-publish --prepare \
    --organization https://dev.azure.com/<sua-org> --project <projeto> --plan <test-plan> --auth azure-cli
```

Revise a prévia (organização, projeto, Test Plan, quantidades de CREATE/UPDATE/CONFLICT, `DELETE operations 0`). Só então:

```text
/ftd-azure-publish --apply ./ftd-output/output/azure/publication-plan.json --auth azure-cli
```

- `--prepare` mostra primeiro qual execução e qual digest canônico serão usados, depois só lê o destino e gera `publication-plan.json` preso a ele.
- `--apply` confere de novo o destino e as versões remotas e só escreve depois que você digita `PUBLISH <projeto> / <plano>` (ou passa `--approved` em modo não interativo).
- O destino nunca é adivinhado, nada é apagado, Test Cases que a FTD não gerencia não são sobrescritos e credenciais nunca são salvas. Detalhes: [`entrypoints/azure-publish.md`](entrypoints/azure-publish.md).

## Como funciona

```text
start       (runtime)  escopo → fontes e papéis → identificadores oficiais → idioma → testes existentes
reading     (leitores) catálogos factuais por fonte (reaproveitados se a fonte não mudou)
design      (modelo)   requisitos → claims atômicos → TCs Acceptance → baseline normativo congelado
expansion   (modelo)   17 dimensões, erros de operador, falhas, testes existentes, jornadas E2E (só adiciona)
procedures  (modelo)   passos executáveis, fixtures semânticas, pendências, automação
finalize    (runtime)  8 gates → estado canônico → HTML / JSON / Markdown → prova de publicação
```

Cada estágio do modelo é validado pelo runtime; um estágio inválido é rejeitado com todos os problemas de uma vez. Design, Expansion e Procedures são raciocínio semântico — scripts que geram payloads por template são rejeitados.

- **Escopo:** só as fontes selecionadas; um diretório é recursivo apenas dentro dele.
- **Papéis:** `FUNCTIONAL_AUTHORITY` (o que deve acontecer), `TECHNICAL_CONTEXT` (como chegar lá), `IMPLEMENTATION_EVIDENCE` (o que existe), `TEST_ASSET` (testes existentes: desafiam a suíte, nunca são autoridade).
- **Idioma:** o da autoridade, salvo pedido explícito.

## Saídas

```text
./ftd-output/
|-- output/
|   |-- report.html            relatório offline: por requisito, famílias, E2E, carga, físicos, chaos, todos
|   |-- test-cases.json        índice: requisitos, cobertura, gaps, gates
|   |-- test-cases/TC-XXX.json fonte de verdade de cada Test Case
|   |-- test-cases-md/         versão Markdown de cada Test Case
|   |-- organization.json      grupos e ordem de execução (referências, sem cópias)
|   |-- execution-plan.md      cada grupo com seus casos em ordem de execução
|   |-- questions.json
|   |-- chaos/<id>/            com /ftd-chaos
|   `-- azure/                 com /ftd-azure (e o plano de /ftd-azure-publish)
|-- diagnostics/               com --diagnostics
`-- .ftd/runs/<run-id>/        estado privado da execução
```

## Segurança

- A FTD só lê as fontes que você seleciona e nunca executa o código delas.
- `/ftd-azure` nunca se conecta a nada. Só `/ftd-azure-publish --apply` escreve no Azure DevOps, depois de um destino explícito, um plano revisado e sua aprovação. Não existe operação de exclusão.
- Credenciais do Azure são usadas só em tempo de execução (sessão do Azure CLI, login interativo Microsoft Entra ou uma variável de ambiente que você nomeia) e nunca são gravadas.

## Avançado

- Contratos e referências: [`SKILL.md`](SKILL.md), [`references/workflow.md`](references/workflow.md), [`references/stage-contracts.md`](references/stage-contracts.md), [`references/output-contract.md`](references/output-contract.md), [`references/validation.md`](references/validation.md).
- Passos internos (o `/ftd-gen` já orquestra tudo; use só para depurar):

```bash
python scripts/pipeline.py start --workspace <raiz> --source "docs/requisitos.pdf=FUNCTIONAL_AUTHORITY" \
    --source "src=IMPLEMENTATION_EVIDENCE" --artifact-root <destino> --run-id <id>
python scripts/pipeline.py submit --run <run> --stage design --file design.json      # depois expansion, procedures
python scripts/pipeline.py finalize --run <run>
python scripts/pipeline.py verify --run <run>
```

- Validar e testar:

```bash
python -m pip install -r requirements.txt
python scripts/validation.py <destino>/output --manifest <destino>/.ftd/runs/<run-id>/run-manifest.json
python scripts/benchmark.py packs           # seis packs sintéticos multi-domínio
python -m unittest discover -s tests
```

## Limites

A FTD não executa testes, não cria Shared Steps, não faz indexação global do repositório e, na publicação, não apaga nem move nada no Azure DevOps.

Veja também [`CHANGELOG.md`](CHANGELOG.md), os [guias de migração](docs/migrations/README.md) e o [histórico](docs/history/v2.3-simplification-report.md).

## License and Attribution

The MIT license and required copyright notice are preserved in `LICENSE`. Adaptation details remain in `ATTRIBUTION.md`.
