# Functional Test Designer

Agent Skill para projetar Test Cases funcionais manuais, rastreáveis e executáveis a partir somente das fontes explicitamente selecionadas pelo usuário.

## Objetivo

Transformar requisitos, documentação, código selecionado e artefatos de QA em Test Cases independentes com passos claros, `Action + Expected Result`, rastreabilidade e cobertura comportamental verificável.

A skill foi feita para ser simples de usar: o usuário informa o que quer analisar e quais fontes entram no escopo; a skill cuida do restante.

Autoridade funcional define o comportamento obrigatório. Outras evidências explicitamente selecionadas podem enriquecer caminhos de execução, dados, observabilidade e desenho de cenários sem se tornarem verdade normativa. Um TC pode conter vários steps ordenados quando um único cenário independente exige uma sequência para alcançar o resultado.

Cada cenário com execução e Pass/Fail independentes gera seu próprio TC. Vários steps pertencem ao mesmo TC somente quando formam um fluxo sequencial e os passos posteriores dependem do estado produzido pelos anteriores.

## Como funciona

```text
Fontes selecionadas pelo usuário
            ↓
        Scope Lock
            ↓
Entendimento do papel de cada fonte
            ↓
      Coverage Points
            ↓
         Cenários
            ↓
  Test Cases independentes
            ↓
      Validação JSON
            ↓
 Markdown + Mermaid por TC
            ↓
     Relatório HTML offline
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

Quando `Diagnostic: true` é usado, métricas separadas são escritas em `diagnostics/`, com tempos, contagens, escopo analisado, releituras e overhead, sem copiar o conteúdo das fontes.

Antes da finalização, uma auditoria source-first por RF/RN procura claims normativos omitidos independentemente do mapeamento clause→CP; uma única recuperação passa novamente pelo pipeline completo. A análise Cross-RF apenas sinaliza sobreposição e possíveis duplicatas para revisão, sem mesclar ou remover TCs automaticamente.

Claims preservam efeitos e alternativas observáveis de forma atômica, inclusive regras RN/CU explicitamente aplicáveis e disponíveis no escopo. Steps seguem a complexidade natural do caminho documentado, enquanto o relatório offline permanece uma projeção determinística e leve do JSON validado.

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
examples/                      Exemplo sintético multi-source
tests/                         Testes de escopo, contrato e renderização
```

## Limites atuais

A skill não automatiza testes, não cria Shared Steps, não faz indexação automática do repositório e não integra diretamente com APIs de Test Management. O contrato dos TCs permanece simples de adaptar futuramente para TMS/MCP, preservando `title`, prioridade, preconditions e `steps` com `Action + Expected Result`.

## License and Attribution

The MIT license and required copyright notice are preserved in `LICENSE`. Adaptation details remain in `ATTRIBUTION.md`.
