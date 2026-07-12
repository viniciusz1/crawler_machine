# ADR 0002: Persistência de Prospects no Postgres

## Status

Accepted

## Context

O módulo `prospecting` descobre imobiliárias candidatas via Google Places API a partir de uma lista manual de cidades (`Cidade,UF`). Atualmente ele gera apenas um YAML local para revisão humana, sem persistência. Isso faz com que execuções repetidas para as mesmas cidades re-descubram os mesmos lugares, consumindo cota da API e gerando trabalho de revisão duplicado.

Há também o risco de conflito: uma imobiliária prospectada em uma cidade pode aparecer novamente em outra cidade, e sem uma base centralizada o operador não tem como saber que ela já foi avaliada.

A base do crawler já possui tabelas no schema `crawler` (`crawler_runs`, `discovery_runs`, `schema_runs`, `raw_properties`, `market_properties`), todas criadas e versionadas fora deste repositório (tipicamente por um serviço backend ou DBA). Adicionar uma tabela `prospects` nesse mesmo schema aproveita a infraestrutura existente.

## Decision

Persistir os resultados de prospecção na tabela `crawler.prospects` e usar essa tabela para deduplicar domínios em execuções futuras.

### Princípios

- **Unicidade por domínio raiz**: a chave natural é `root_domain(base_url)`, não o `google_place_id`. Duas filiais da mesma imobiliária apontando para o mesmo site são tratadas como um único prospect.
- **Todos os status são deduplicados**: se um domínio já consta na base, ele é excluído de novas queries independentemente de estar `candidate` ou `rejected`.
- **Flag `--force`**: permite reprocessar domínios já prospectados. Com `--force`, o registro existente é atualizado por upsert real (`INSERT ... ON CONFLICT (root_domain) DO UPDATE`); os dados mais recentes prevalecem.
- **Persistência cidade por cidade**: após classificar os lugares de uma cidade, os candidatos (`candidate` e `rejected`) são salvos antes de partir para a próxima cidade.
- **Resiliência parcial**: falhas de persistência em uma cidade não interrompem a execução. O comando continua com as demais cidades e reporta quais não foram salvas.
- **Modo degradado**: quando o Postgres não está configurado, `prospecting find` executa no modo legado e gera apenas o YAML.
- **Separação de responsabilidades**: a interface do repositório vive no módulo `prospecting`; a implementação Postgres fica no pacote `sink`. A tabela é criada e versionada fora deste repositório.

### Schema

```sql
CREATE TABLE crawler.prospects (
    id SERIAL PRIMARY KEY,
    root_domain TEXT NOT NULL UNIQUE,
    source_name TEXT NOT NULL,
    base_url TEXT,
    google_place_id TEXT NOT NULL,
    name TEXT NOT NULL,
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('candidate', 'rejected')),
    reject_reason TEXT,
    phone TEXT,
    address TEXT,
    place_payload JSONB,
    prospecting_run_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Interface mínima do repositório

```python
class ProspectRepository(ABC):
    @abstractmethod
    def filter_new_places(self, places: list[Place], force: bool = False) -> list[Place]: ...

    @abstractmethod
    def save_candidates(self, candidates: list[Candidate], run_id: str) -> None: ...
```

## Consequences

### Positivas

- Elimina redescoberta de imobiliárias já prospectadas, economizando cota da Google Places API.
- Permite executar `prospecting find` periodicamente para a mesma cidade sem poluir o YAML com candidatos repetidos.
- Centraliza o histórico de decisões (`candidate`/`rejected`) para auditoria.
- Facilita futuras features como "listar prospects pendentes" ou "exportar candidatos aprovados".

### Negativas

- Exige nova migration no serviço que gerencia o banco de dados.
- Adiciona uma dependência de banco ao módulo de prospecção.
- A deduplicação por domínio raiz pode perder filiais reais que usam o mesmo site mas têm conteúdo local diferente.
- A regra "todos os status ignorados" significa que um domínio rejeitado por erro temporário só volta com `--force`.

## Alternatives considered

- **Deduplicar por `google_place_id`**: descartado. Duas filiais da mesma imobiliária seriam prospects diferentes, mas o crawler as trataria como o mesmo `source_name`, causando conflito.
- **Ignorar apenas status `crawled`**: descartado. Rejeitados por agregador voltariam eternamente, desperdiçando cota.
- **Tabela `prospecting_runs` com FK**: descartado para MVP. O `prospecting_run_id` textual agrupa execuções sem exigir mais uma tabela.
- **Persistir apenas `candidate`**: descartado. Rejeitados por agregador precisam ser lembrados para não serem reprocessados.
