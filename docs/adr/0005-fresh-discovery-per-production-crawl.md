# Novo discovery por crawl de produção

Cada crawl de produção gera por padrão um Snapshot de Discovery novo, pois reutilizar indefinidamente o último conjunto de URLs impede encontrar anúncios novos e mantém imóveis removidos. O Plano da Operação pode reutilizar explicitamente um snapshot anterior para reprodução ou diagnóstico, e retentativas preservam o snapshot da operação original. Essa escolha privilegia atualidade do estoque sobre economia de discovery; resultados vazios ou regressivos passam pelo Portão de Qualidade em vez de provocar fallback silencioso para URLs antigas.

A seleção de snapshots anteriores é manual, fica registrada no Plano da Operação e é limitada à mesma Crawl Agency; agendamentos continuam gerando discovery novo.
