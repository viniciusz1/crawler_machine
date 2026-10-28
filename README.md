# crawler-machine

Sistema especializado em extrair dados de imobiliárias a partir da URL base de um site.

## Funcionamento

O Crawler Machine roda como um **worker**. A Admin Area enfileira Operações do Crawler no Postgres; o worker reivindica cada operação, executa e grava o resultado de volta no banco. Não existem comandos de terminal para rodar etapas isoladas: toda execução passa pelo worker.

Tipos de operação executados pelo worker (`crawler_machine/worker/runner.py`):

- **Discovery**: descobre URLs de imóveis a partir da URL base (`URLDiscoverer`, com sitemap, `DomainMapper` do Crawl4AI e a estratégia Playwright de listagem/paginação).
- **Sugestão de URL de exemplo**: encontra pela home uma página de imóvel individual (`HomeSampleFinder`).
- **Geração de Perfil de Extração**: gera os schemas XPath/CSS com IA a partir da URL de exemplo (`SchemaGenerator`).
- **Crawl de Validação**: valida um Perfil de Extração candidato (`ProfileValidationExecutor`).
- **Crawl de produção**: extrai e normaliza os imóveis das URLs descobertas (`ProductionCrawlExecutor`, `CrawlEngine`, `DataNormalizer`).
- **Prospecção**: busca imobiliárias candidatas em uma cidade via Google Places (`ProspectingExecutor`; requer `GOOGLE_PLACES_API_KEY`).

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

Para a prospecção, adicione também `GOOGLE_PLACES_API_KEY`. Sem ela, o worker sobe normalmente, mas não executa operações de prospecção.

> **A fonte de verdade dos dados do crawler é o Postgres.** Operações, snapshots de discovery, perfis de extração, dados brutos, imóveis normalizados e artefatos são lidos e gravados no banco.

Os campos padrão a serem extraídos e as configurações globais de LLM/crawler ficam em `config/domain.json` (passado ao worker via `--config`), servindo de base para a geração de schemas.

## Fluxo pela interface administrativa

A Admin Area em `http://localhost:3000/admin/crawler` cria e acompanha operações; ela não executa o scraping dentro do navegador. Um worker do Crawler Machine precisa estar ativo para reivindicar as operações enfileiradas no Postgres.

Com o backend e o frontend em execução (`./start.sh` na raiz do repositório), inicie o worker em outro terminal:

```bash
cd crawler-machine
source .venv/bin/activate
python -m crawler_machine worker --worker-key local-dev --version dev
```

O arquivo `.env` do Crawler Machine deve ter as variáveis `DB_*` configuradas para o Postgres da aplicação. No ambiente local padrão, use `DB_HOST=localhost` e `DB_PORT=7777`.

### Onboarding de uma nova Crawl Agency

1. Em **Configurações**, ative um **Contrato de Dados de Mercado** e uma **Política de Qualidade**.
2. Em **Crawl Agencies**, cadastre a imobiliária.
3. Em **Operações → Novo Discovery**, selecione a Crawl Agency e o contrato ativo e clique em **Enfileirar Discovery**.
4. Ao terminar, abra o detalhe da Crawl Agency. Em **Onboarding**, use **Sugerir pela home** (ou informe uma URL de imóvel), confirme a URL e clique em **Gerar Perfil Candidato**.
5. Em **Perfis de Extração**, execute **Rodar Crawl de Validação**. Se o relatório estiver elegível, informe o motivo, aprove o perfil, ative-o e então ative a Crawl Agency.
6. Em **Novo crawl de produção**, prefira **Gerar novo Discovery** (ou escolha um snapshot anterior), selecione o perfil e clique em **Rodar Crawl**.

O andamento aparece em **Operações**. Ao concluir, use **Visualizar dados do crawl** ou consulte o snapshot na página da Crawl Agency. Se uma operação permanecer em `queued`, confirme que o worker está em execução e consegue acessar o banco.

## Worker

```bash
python -m crawler_machine worker --worker-key local-dev --version dev
```

Opções:

- `--worker-key`: identidade estável do worker (padrão: hostname).
- `--version`: versão implantada, registrada para observabilidade.
- `--poll-seconds`: intervalo de espera quando a fila está vazia (padrão: `3.0`).
- `--once`: processa no máximo uma operação e encerra.
- `--config`: caminho do `domain.json` (padrão: `config/domain.json`).

## Testes

```bash
python -m pytest tests/ -v
```

## Estrutura de pastas

```
crawler-machine/
├── crawler_machine/
│   ├── __main__.py
│   ├── cli/                 # entrypoint Typer (comando `worker`)
│   ├── worker/              # runner, store Postgres e executores de operação
│   ├── discovery/           # URLDiscoverer, sitemap e Playwright (items_catalog/)
│   ├── extraction/          # CrawlEngine e estratégias de extração
│   ├── normalization/       # DataNormalizer e normalizadores por campo
│   ├── prospecting/         # Google Places, filtros e HomeSampleFinder
│   ├── sink/                # configuração e conexão Postgres
│   ├── catalog.py
│   ├── config.py
│   ├── image_policy.py
│   └── schema_generator.py
├── config/
│   └── domain.json
├── docs/adr/
├── tests/
├── .env.example
├── CONTEXT.md
├── README.md
└── requirements.txt
```


## Diagnóstico de crawls de produção

O worker publica observações versionadas em `crawler.operation_diagnostics` durante
as operações: discovery, coleta, tentativas de estratégias, normalização e
persistência. O contrato e as partições são mantidos pelas migrations do Laravel;
aplique primeiro a API do PR viniciusz1/ia-imob#146. Não há novas variáveis de
produção nem outro serviço de mensageria.

As evidências são vinculadas à operação antes da criação do Crawl Run, preservando
tentativas e falhas recuperadas por fallback. UUID e timestamp estáveis permitem
entrega idempotente; somente o worker com lease vigente pode gravar. O engine usa
callbacks opcionais e mantém o formato dos resultados existentes. A cobertura por
campo inclui URLs rejeitadas; presença de campo não comprova exatidão semântica.

A instrumentação não acrescenta tentativas recuperadas ao error_count usado pelo
Portão de Qualidade. A interface de lotes e a avaliação/publicação pertencem ao
Laravel. Agendamentos automáticos não são agrupados nesta entrega.

Validação focada:

```bash
python3 -m pytest tests/test_extraction_engine.py tests/test_production_crawl.py tests/test_worker.py tests/test_worker_adapters.py
```
