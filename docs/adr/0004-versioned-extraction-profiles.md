# Perfis de Extração versionados e ativados explicitamente

Cada Crawl Agency usa um Perfil de Extração versionado que agrupa schemas XPath/CSS, estratégias, campos esperados, URL de amostra e parâmetros relevantes. Uma versão gerada é candidata até passar por Crawl de Validação e aprovação humana; somente versões aprovadas podem orientar produção, e toda operação registra a versão selecionada. O perfil ativo é o padrão, mas um Platform Admin pode selecionar explicitamente outra versão anteriormente aprovada. Escolhemos versões imutáveis e rollback explícito em vez do `latest schema` mutável para evitar que uma regeneração ainda não validada afete crawls de produção, ao custo de preservar mais histórico e introduzir um fluxo de ativação.

Seleções manuais ficam restritas a versões da mesma Crawl Agency e são congeladas no Plano da Operação. Agendamentos sempre usam o perfil ativo; gerar um novo perfil encadeia geração e validação, mas não autoriza seu uso em produção antes da aprovação.

O Crawl de Validação processa até 20 URLs distribuídas pelo Snapshot de Discovery selecionado, ou todas quando o snapshot tiver menos de 20. A revisão humana recebe cobertura por campo, valores brutos e normalizados e erros de extração antes de aprovar ou rejeitar o perfil candidato.

Um perfil candidato somente fica elegível para aprovação quando ao menos 80% das URLs de validação produzem registros normalizados válidos, cada campo obrigatório da versão fixada do Contrato de Dados de Mercado possui cobertura mínima de 90% antes do filtro e não existe falha bloqueante. Alertas não impedem a decisão humana. A elegibilidade não aprova nem ativa o perfil automaticamente.

Regeneração assistida pelos erros do relatório e comparação automática entre versões ficam fora do escopo inicial. Quando um perfil falhar ou for reprovado, a correção ocorre pela criação manual de uma nova versão candidata, sem alterar a versão anterior.
