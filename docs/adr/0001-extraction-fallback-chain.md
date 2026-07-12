# ADR 0001: Cadeia de Fallback de Extração

## Status

Accepted

## Context

O `crawler-machine` extrai dados de imobiliárias usando schemas de extração (XPath/CSS) gerados por IA a partir de uma única URL de amostra. Dados reais mostram que esse modelo falha frequentemente para campos obrigatórios mínimos — especialmente `valor` — quando o seletor gerado não se aplica a todos os layouts de página do site.

Exemplos observados em produção:

- `www-imobiliariajaragua-com-br`: 100% dos registros sem `valor` porque o seletor `//h6[@class='preco-imovel']` não bateu nas páginas reais.
- `imobiliariaurbana-com-br`: 71,8% dos registros sem `valor`.
- `singular-imb-br`: 98,9% dos registros sem `valor`.

O normalizador só pode converter o que o crawler entrega. Quando o campo não vem da extração estruturada, não há recuperação possível. Era necessário um mecanismo de fallback que tentasse múltiplas formas de extração antes de desistir de uma página.

## Decision

Adotar uma **cadeia de fallback de extração** com cinco estratégias, executadas em ordem fixa:

1. **XPath** — schema gerado por IA com seletores XPath.
2. **CSS** — schema gerado por IA com seletores CSS.
3. **Fit Markdown Regex** — extrai padrões (preço, área, quartos etc.) do markdown filtrado da página.
4. **Fit Markdown LLM** — mini-LLM sobre o markdown filtrado para campos semânticos ainda faltantes.
5. **LLM full HTML** — `LLMExtractionStrategy` nativa do Crawl4AI sobre o HTML completo, como último recurso.

### Princípios da cadeia

- Cada estratégia tenta preencher **apenas os campos obrigatórios mínimos ainda não encontrados**.
- O HTML bruto da primeira requisição é **guardado e reaproveitado** pelas etapas seguintes, evitando requests repetidos.
- Apenas a **primeira estratégia que faz requisição HTTP possui retry**.
- A ativação das etapas que consomem tokens (Fit Markdown LLM e LLM full HTML) é **opt-in** via `config/domain.json` e flag de CLI.
- O artefato `schema.json` passa a conter ambos os schemas: `schemas.xpath` e `schemas.css`.
- Cada registro bruto carrega um `ExtractionTrace` indicando qual estratégia forneceu cada campo.

### Defaults

Por padrão, as seguintes estratégias ficam ligadas:

- XPath
- CSS
- Fit Markdown Regex

Fit Markdown LLM e LLM full HTML ficam desligados por padrão.

## Consequences

### Positivas

- Aumenta a cobertura de extração de campos obrigatórios sem depender de um único seletor.
- Permite debugar qual estratégia salvou cada campo via `ExtractionTrace`.
- Estratégias de fallback são plugáveis; novas podem ser adicionadas sem alterar a engine.
- HTML reaproveitado reduz requests e risco de bloqueio.

### Negativas

- Aumenta a complexidade do crawler: mais classes, mais testes, mais configuração.
- Dois schemas por site aumentam o custo de geração (duas chamadas de LLM).
- LLM full HTML é caro; por isso é opt-in.
- Muda o formato do `schema.json` e do `schema_runs` no Postgres (dois registros por run).

## Alternatives considered

- **JSON-LD parser**: descartado. Embora útil, não é uma estratégia nativa do Crawl4AI e exigiria parser customizado por site.
- **Apenas um schema com múltiplos seletores**: descartado. Não resolve o problema quando o layout varia entre páginas do mesmo site.
- **LLM sobre HTML direto, sem Fit Markdown**: descartado. O markdown filtrado reduz tokens e ruído antes de acionar o LLM.
- **Manter `ImovelCrawler` como legado**: descartado. Substituição direta por `CrawlEngine` evita dívida técnica.
