# ADR 0003: Reorganização da Estrutura de Output

## Status

Accepted

## Context

O diretório `output/` acumulou três categorias distintas de artefatos na mesma raiz:

1. Execuções do crawler: `output/<domínio>/<timestamp>/{discovered,schema,raw,normalized,rejected,errors,quality_report}.json`
2. Relatórios de batch: `output/batch_report_<timestamp>.json`
3. Resultados de prospecção: `output/prospecting/candidatos_<timestamp>.yaml`

Essa mistura dificulta a navegação, a limpeza automatizada e a descoberta de artefatos. Scripts e operadores precisam conhecer convenções diferentes para cada tipo de saída.

## Decision

Reorganizar `output/` em pastas por tipo de artefato:

```
output/
├── runs/<domínio>/<timestamp>/...     # artefatos de execução do crawler
├── prospecting/<timestamp>/candidates.yaml
└── batch-reports/<timestamp>.json
```

### Princípios

- **Pasta `output/runs/`**: concentra todos os artefatos gerados por execuções do pipeline (`discovered.json`, `schema.json`, `raw.json`, `normalized.json`, `rejected.json`, `errors.json`, `quality_report.json`).
- **Pasta `output/prospecting/`**: concentra YAMLs de candidatos gerados por `prospecting find`.
- **Pasta `output/batch-reports/`**: concentra JSONs de relatório do comando `clone-das-sombras`.
- **Mudança hard**: não haverá compatibilidade com caminhos antigos, symlinks, fallback nem aviso de deprecação. A estrutura anterior deixa de existir para novas execuções.
- **Atualização do `OutputPath`**: a classe central `OutputPath` passa a usar `output/runs/` como base para execuções do crawler.

## Consequences

### Positivas

- Separação clara entre artefatos de crawler, prospecção e batch.
- Facilita limpeza e rotação por tipo (`rm -rf output/prospecting/2026*`).
- Reduz poluição na raiz de `output/`.
- Torna óbvio para novos desenvolvedores onde cada artefato mora.

### Negativas

- Quebra scripts, ferramentas e documentação que dependem dos caminhos antigos.
- Requer atualização de testes que verificam caminhos de arquivo.
- Histórico de execuções antigas continua nos caminhos antigos, criando uma transição visual desorganizada até que sejam arquivadas ou removidas.

## Alternatives considered

- **Manter estrutura atual**: descartado. A raiz de `output/` ficaria cada vez mais confusa com o crescimento de domínios e execuções.
- **Reorganizar parcialmente (apenas prospecting e batch-reports)**: descartado. Deixaria os runs na raiz, mantendo a inconsistência visual.
- **Mudança com compatibilidade legada (fallback/symlinks/deprecação)**: descartado. Adicionaria código temporário e dívida técnica para um sistema ainda em evolução.
