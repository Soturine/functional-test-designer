# Functional Test Designer V1.2

Agent Skill para projetar Test Cases funcionais manuais, rastreáveis e executáveis a partir somente das fontes explicitamente selecionadas pelo usuário.

## Objetivo

Transformar requisitos, documentação, código selecionado e artefatos de QA em Test Cases independentes com passos claros, `Action + Expected Result`, rastreabilidade e cobertura comportamental verificável.

A skill foi feita para ser simples de usar: o usuário informa o que quer analisar e quais fontes entram no escopo; a skill cuida do restante.

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

Em resumo:

```text
LLM pode interpretar evidências.
LLM não deve inventar autoridade.
```

## Uso

Exemplo simples:

```text
Use a functional-test-designer para gerar os Test Cases de:

docs/requisitos.pdf

Diagnostic: true.
```

Exemplo com documentação e código selecionado:

```text
Use a functional-test-designer.

Analise somente:
- docs;
- dentro de backend, somente rfid.

Gere os Test Cases e aponte possíveis divergências.
Diagnostic: true.
```

A skill pode analisar, quando explicitamente selecionados, requisitos, especificações, documentação funcional/técnica, código-fonte, configuração, Test Cases existentes, planos de teste e outros artefatos relevantes à tarefa.

## Saída

```text
output/
|-- test-cases.json
|-- questions.json
|-- report.html
|-- test-cases/
|   `-- TC-XXX.json
`-- test-cases-md/
    `-- TC-XXX.md
```

Cada TC possui um JSON individual e um Markdown correspondente. O Markdown inclui o fluxo Mermaid do caso, e o HTML agrega os TCs em uma visão amigável com seus artefatos associados.

Diagnósticos opcionais ficam em `diagnostics/` e registram tempos, contagens e evidências de respeito ao escopo, sem copiar o conteúdo das fontes.

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
scripts/validate_output.py     Validação JSON e cross-file
scripts/render_markdown.py     Markdown determinístico por TC
scripts/render_report.py       Relatório HTML offline
scripts/diagnostics.py         Diagnóstico opcional de execução
examples/                      Exemplo sintético multi-source
tests/                         Testes de escopo, contrato e renderização
```

## Limites atuais

A skill não automatiza testes, não cria Shared Steps, não faz indexação automática do repositório e não integra diretamente com a API do Azure DevOps. O contrato dos TCs permanece simples de adaptar futuramente para TMS/MCP, preservando `title`, prioridade, preconditions e `steps` com `Action + Expected Result`.

## License and Attribution

The MIT license and required copyright notice are preserved in `LICENSE`. Adaptation details remain in `ATTRIBUTION.md`.
