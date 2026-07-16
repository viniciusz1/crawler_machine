# Preservar decisões humanas ao reconsultar domínios conhecidos

Uma Reconsulta de Domínio atualiza somente os dados novamente descobertos sobre um Prospect; ela não sobrescreve sua classificação ou Revisão do Prospect. Quando o domínio já pertence a uma Crawl Agency, os dados novos aparecem como diferenças sugeridas e nunca alteram cadastro, configuração ou estado automaticamente. Isso substitui a semântica de upsert integral do `--force` no ADR 0002 e aceita mais lógica de merge para impedir que uma consulta externa reverta decisões humanas.
