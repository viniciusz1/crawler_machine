from __future__ import annotations

import re

DEFAULT_PROPERTY_PATTERNS = [
    r"/imovel/",
    r"/imovel-",
    r"/imoveis/detalhes",
    r"/\d{3,}/?(?:\?.*)?$",
    r"/detalhes_(?:loc|vd)\.php\?imovel=\d+",
    r"/(?:comprar|alugar|vender)/[^/]+/\d+",
    r"/(?:comprar|alugar|vender)/.+",
]

EXCLUDED_NON_PROPERTY_PATTERNS = [
    r"^/imoveis/?$",
    r"^/imoveis/(?:comprar|alugar|aluguel|vender|locacao|venda)/?$",
    r"^/imovel/(?:comprar|alugar|aluguel|vender|locacao|venda)/?$",
    r"^/(?:comprar|alugar|aluguel|vender|locacao|venda)/?$",
    r"^/(?:venda|aluguel|locacao)/(?:imovel|apartamento|casa|terreno|cobertura|comercial|galpao)",
    r"/filtro/",
    r"cadastr",
    r"encomend",
    r"solicite",
    r"anuncie",
    r"financi",
    r"trabalhe-conosco",
    r"ouvidoria",
    r"nossa-equipe",
    r"quem-somos",
    r"conheca-a-cidade",
    r"nossos-diferenciais",
    r"nossos-profissionais",
    r"como-alugar",
    r"indice-de-reajuste",
    r"assessoria-juridica",
    r"quero-alugar-ou-vender",
    r"area-do-cliente",
    r"/whatsapp",
    r"/blog(?:/|$)",
    r"/corretores",
    r"/institucional",
    r"/documentos",
    r"/condominios/?$",
    r"/busca/?$",
    r"/contato",
    r"/sobre",
    r"/empresa",
    r"/favorito",
    r"/login",
    r"/admin",
    r"/politica",
    r"/privacidade",
    r"/termos",
    r"todos-os-bairros",
    r"todas-as-opcoes",
    r"ordenacao=",
    r"(?:^|[?&])(pagina|page|pg|p)=\d+",
    r"(?:/|-|_)(?:page|pagina)(?:/|-|_)\d+/?$",
]

NEXT_TEXT_PATTERNS = re.compile(
    r"^(?:pr[oó]xim[ao](?:\s+p[aá]gina)?|seguinte|avan[cç]ar|next(?:\s+page)?|"
    r">|>>|»|›|→|pr[oó]xim[ao]\s*(?:>|>>|»|›|→))$",
    re.IGNORECASE,
)

EXPLICIT_NEXT_WORD_RE = re.compile(
    r"^(?:pr[oó]xim[ao](?:\s+p[aá]gina)?|seguinte|next(?:\s+page)?|"
    r"pr[oó]xim[ao]\s*(?:>|>>|»|›|→))$",
    re.IGNORECASE,
)

LOAD_MORE_TEXT_PATTERNS = re.compile(
    r"(?:carregar\s+mais|ver\s+mais\s+im[oó]veis|mostrar\s+mais|"
    r"mais\s+im[oó]veis|exibir\s+mais|load\s+more|carregar\s*\+)",
    re.IGNORECASE,
)

VER_MAIS_EXACT_RE = re.compile(r"^(?:ver\s+mais|veja\s+mais)$", re.IGNORECASE)

PAGINATION_CONTAINER_RE = re.compile(
    r"(?:paginat|paginacao|pagina[cç][aã]o|page-numbers|wp-pagenavi|nav-links|pager|"
    r"jetpagination|PageNumber|BtnShowMoreImovel|BoxBtnShowMoreImovel)",
    re.IGNORECASE,
)

PAGINATION_NEXT_CLASS_RE = re.compile(
    r"(?:jetpagination__next|list__next-btn|page-next|next-page|pagination-next)",
    re.IGNORECASE,
)

NON_PAGINATION_CONTROL_RE = re.compile(
    r"(?:owl-|slick-|swiper-|carousel|slider|banner|card-img|card-btn|modal|"
    r"agendar|ag-data|cookie|whatsapp|wpp|primeiraPagina|ultimaPagina|"
    r"first-page|last-page|previous|prev-btn|botao_tipo_busca)",
    re.IGNORECASE,
)

LOAD_MORE_CLASS_RE = re.compile(
    r"(?:load-more|loadmore|carregar-mais|btn-more|show-more|BtnShowMoreImovel|infinite-scroll)",
    re.IGNORECASE,
)

PROPERTY_CARD_LINK_CLASS_RE = re.compile(
    r"(?:ImovelLinkClick|VejaMais|ui__card-link|meuLink|card-imovel|imovel-card|property-card)",
    re.IGNORECASE,
)

PAGE_QUERY_KEYS = ("pagina", "page", "pg", "p")
PAGE_PATH_RE = re.compile(
    r"(?:/|-|_)(?:page|pagina)(?:/|-|_)(\d+)(?:/|$)",
    re.IGNORECASE,
)

LISTING_ENTRYPOINT_PATH_RE = re.compile(
    r"^/(?:imoveis|imovel/(?:comprar|alugar|aluguel|vender|locacao|venda)|"
    r"imoveis/(?:comprar|alugar|aluguel|vender|locacao|venda|a-venda|para-alugar)|"
    r"comprar|alugar|aluguel|vender|locacao|venda|busca|buscar-imoveis)/?$",
    re.IGNORECASE,
)

LISTING_ENTRYPOINT_TEXT_RE = re.compile(
    r"(?:ver\s+todos(?:\s+os)?\s+im[oó]veis|todos\s+os\s+im[oó]veis|"
    r"ver\s+mais\s+im[oó]veis|buscar\s+im[oó]veis|nossos\s+im[oó]veis|"
    r"im[oó]veis\s+[aà]\s+venda|im[oó]veis\s+para\s+alugar|"
    r"^im[oó]veis$|^comprar$|^alugar$|^venda$|^loca[cç][aã]o$)",
    re.IGNORECASE,
)
