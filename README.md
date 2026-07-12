# crawler-machine

Sistema especializado em extrair dados de imobiliárias a partir da URL base de um site.

## Funcionamento

O sistema executa quatro etapas sequenciais:

1. **Discovery**: descobre URLs a partir da URL base usando `DomainMapper` do Crawl4AI.
2. **Schema generation**: gera um schema de extração (XPath/CSS) com IA a partir de uma URL de exemplo.
3. **Crawling**: extrai dados estruturados das URLs descobertas usando o schema gerado.
4. **Normalization**: converte valores brutos em tipos úteis (`int`, `float`, `currency`, `string`).

Cada etapa é representada por uma classe Python independente:

- `URLDiscoverer`
- `SchemaGenerator`
- `ImovelCrawler`
- `DataNormalizer`

A orquestração é feita pela classe `Pipeline` e a interface terminal é fornecida pela CLI.

## Instalação

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuração

Copie o exemplo de variáveis de ambiente:

```bash
cp .env.example .env
```

Edite `.env` e adicione sua chave da API DeepSeek e os dados de acesso ao Postgres:

```bash
DEEPSEEK_API_KEY=sk-sua-chave-aqui

DB_HOST=localhost
DB_PORT=5432
DB_DATABASE=ia_imob
DB_USERNAME=crawler
DB_PASSWORD=password
```

> **A fonte de verdade dos dados do crawler é o Postgres.** Os artefatos JSON em `output/` ainda são gerados para debug, mas as URLs descobertas, schemas gerados, dados brutos e imóveis normalizados são lidos e gravados no banco (`discovery_runs`, `schema_runs`, `raw_properties`, `market_properties`).

Os campos padrão a serem extraídos e as configurações globais de LLM/crawler continuam em `config/domain.json`, servindo de base para a geração de schemas. O `source_name` usado no banco deve ser escolhido de forma consistente para cada imobiliária.

## Uso

### Pipeline completo

O comando `run` reutiliza URLs e schemas já salvos no banco quando `--source-name` já possui registros `latest`. Para forçar nova geração, use `--regenerate-discovery` e/ou `--regenerate-schema`.

```bash
# Primeiro run: é necessário informar a URL de exemplo para gerar o schema
python -m crawler_machine run https://imbsmart.com.br \
  --source-name imbsmart-com-br \
  --sample-url https://imbsmart.com.br/imovel/exemplo

# Runs seguintes: reutiliza discovery e schema do banco
python -m crawler_machine run https://imbsmart.com.br \
  --source-name imbsmart-com-br
```

`--source-name` é **obrigatório** em todos os comandos que persistem ou leem do banco.

### Batch de imobiliárias

O comando `clone-das-sombras` processa uma lista de imobiliárias definidas em um arquivo YAML. Cada item precisa de `base_url` e `source_name`; `sample_url` é obrigatório apenas na primeira execução, quando ainda não há schema/discovery cacheado no banco.

```bash
python -m crawler_machine clone-das-sombras imobiliarias.yaml
```

Exemplo de `imobiliarias.yaml`:

```yaml
- base_url: https://imbsmart.com.br
  source_name: imbsmart-com-br
  sample_url: https://imbsmart.com.br/imovel/exemplo
- base_url: https://jaraguaimoveis.com.br
  source_name: jaraguaimoveis-com-br
  sample_url: https://jaraguaimoveis.com.br/imovel/exemplo
```

O processamento é sequencial e resiliente: se uma imobiliária falhar, o batch continua com as demais. Ao final, gera `output/batch_report_<timestamp>.json` com o status de cada imobiliária, além dos artefatos normais por imobiliária em `output/<slug>/<timestamp>/`.

### Prospecção de imobiliárias

O comando `prospecting find` busca imobiliárias candidatas em cidades via **Google Places API** — útil para descobrir alvos em cidades onde o sistema ainda não tem cobertura. Requer a variável `GOOGLE_PLACES_API_KEY` no `.env`.

```bash
python -m crawler_machine prospecting find \
  --cities "Joinville,SC;Blumenau,SC" \
  --max-per-city 30
```

A UF é obrigatória (para desambiguar homônimos). O resultado é um **YAML de candidatos para revisão humana** em `output/prospecting/candidatos_<timestamp>.yaml`, com cada entrada classificada como `candidate` ou `rejected` (`aggregator` / `no_website` / `duplicate_domain`). Para incluir uma imobiliária no pipeline, revise os `candidate`, preencha `sample_url` e adicione-os ao YAML do `clone-das-sombras`.

### Etapas isoladas

Descobrir URLs:

```bash
python -m crawler_machine discover https://imbsmart.com.br \
  --source-name imbsmart-com-br \
  --save-to-db
```

Gerar schema:

```bash
python -m crawler_machine schema https://imbsmart.com.br/imovel/exemplo \
  --source-name imbsmart-com-br \
  --save-to-db
```

Crawlear usando arquivos JSON locais (não consulta o banco):

```bash
python -m crawler_machine crawl output/imbsmart-com-br/20260702_120000/schema.json \
  output/imbsmart-com-br/20260702_120000/discovered.json
```

Normalizar dados brutos:

```bash
python -m crawler_machine normalize output/imbsmart-com-br/20260702_120000/raw.json
```

## Saída

Os artefatos de cada execução são salvos em:

```
output/<slug-do-dominio>/<timestamp>/
  discovered.json
  schema.json
  raw.json
  normalized.json
  rejected.json
  quality_report.json
  errors.json
```

O destino principal, no entanto, são as tabelas do Postgres gerenciadas externamente.

## Testes

```bash
python -m pytest tests/ -v
```

## Estrutura de pastas

```
crawler-machine/
├── src/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── config.py
│   ├── crawler.py
│   ├── discoverer.py
│   ├── output.py
│   ├── pipeline.py
│   ├── schema_generator.py
│   ├── catalog.py
│   ├── sink.py
│   └── normalization/
│       ├── __init__.py
│       ├── result.py
│       ├── protocol.py
│       ├── engine.py
│       ├── coercers.py
│       ├── legacy.py
│       └── normalizers/
│           ├── area_normalizer.py
│           ├── city_normalizer.py
│           ├── details_normalizer.py
│           ├── image_normalizer.py
│           ├── integer_normalizer.py
│           ├── neighborhood_normalizer.py
│           ├── property_type_normalizer.py
│           ├── url_normalizer.py
│           ├── value_normalizer.py
│           └── year_normalizer.py
├── config/
│   └── domain.json
├── tests/
│   ├── test_cli.py
│   ├── test_config.py
│   ├── test_crawler.py
│   ├── test_data_normalizer_semantic.py
│   ├── test_discoverer.py
│   ├── test_normalizer.py
│   ├── test_output.py
│   ├── test_pipeline.py
│   ├── test_schema_generator.py
│   ├── catalog_seed.py
│   ├── crawler_schema.py
│   └── test_normalizers/
├── .env.example
├── README.md
├── requirements.txt
└── CONTEXT.md
```
