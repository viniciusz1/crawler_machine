import pytest

from crawler_machine.extermination.exterminator import Exterminator, RejectedRecord


def test_exterminator_keeps_complete_record():
    exterminator = Exterminator()
    record = {
        "bairro": "Centro",
        "cidade": "Jaraguá do Sul",
        "valor": 450_000,
        "tipo_imovel": "Apartamento",
        "url": "https://example.com/imovel/1",
        "imagem": "https://example.com/img.jpg",
    }

    survivors, rejected = exterminator.filter([record])

    assert survivors == [record]
    assert rejected == []


def test_exterminator_rejects_record_with_missing_field():
    exterminator = Exterminator()
    record = {
        "cidade": "Jaraguá do Sul",
        "valor": 450_000,
        "tipo_imovel": "Apartamento",
        "url": "https://example.com/imovel/1",
        "imagem": "https://example.com/img.jpg",
    }

    survivors, rejected = exterminator.filter([record])

    assert survivors == []
    assert len(rejected) == 1
    assert rejected[0].index == 0
    assert rejected[0].missing_fields == ["bairro"]
    assert rejected[0].reason == "missing required fields: bairro"


@pytest.mark.parametrize(
    "empty_value",
    [None, "", "   ", [], {}],
)
def test_exterminator_rejects_record_with_empty_field(empty_value):
    exterminator = Exterminator()
    record = {
        "bairro": empty_value,
        "cidade": "Jaraguá do Sul",
        "valor": 450_000,
        "tipo_imovel": "Apartamento",
        "url": "https://example.com/imovel/1",
        "imagem": "https://example.com/img.jpg",
    }

    survivors, rejected = exterminator.filter([record])

    assert survivors == []
    assert len(rejected) == 1
    assert rejected[0].missing_fields == ["bairro"]


def test_exterminator_preserves_original_index_and_multiple_missing_fields():
    exterminator = Exterminator()
    records = [
        {"bairro": "Centro", "cidade": "Jaraguá do Sul", "valor": 100_000, "tipo_imovel": "Casa", "url": "https://example.com/1", "imagem": "https://example.com/1.jpg"},
        {"cidade": "Jaraguá do Sul", "valor": 200_000, "tipo_imovel": "Apartamento"},
        {"bairro": "Bairro Novo", "cidade": "Joinville", "valor": 300_000, "tipo_imovel": "Casa", "url": "https://example.com/3", "imagem": "https://example.com/3.jpg"},
    ]

    survivors, rejected = exterminator.filter(records)

    assert len(survivors) == 2
    assert survivors[0] == records[0]
    assert survivors[1] == records[2]

    assert len(rejected) == 1
    assert rejected[0].index == 1
    assert rejected[0].record == records[1]
    assert rejected[0].missing_fields == ["bairro", "url", "imagem"]
    assert rejected[0].reason == "missing required fields: bairro, url, imagem"


@pytest.mark.parametrize(
    "empty_images",
    [[], [""], [None], ["", None], ["   "]],
)
def test_exterminator_rejects_record_with_empty_image_list(empty_images):
    exterminator = Exterminator()
    record = {
        "bairro": "Centro",
        "cidade": "Jaraguá do Sul",
        "valor": 450_000,
        "tipo_imovel": "Apartamento",
        "url": "https://example.com/imovel/1",
        "imagem": empty_images,
    }

    survivors, rejected = exterminator.filter([record])

    assert survivors == []
    assert len(rejected) == 1
    assert rejected[0].missing_fields == ["imagem"]


def test_exterminator_keeps_record_with_valid_image_list():
    exterminator = Exterminator()
    record = {
        "bairro": "Centro",
        "cidade": "Jaraguá do Sul",
        "valor": 450_000,
        "tipo_imovel": "Apartamento",
        "url": "https://example.com/imovel/1",
        "imagem": ["https://example.com/img1.jpg", "https://example.com/img2.jpg"],
    }

    survivors, rejected = exterminator.filter([record])

    assert survivors == [record]
    assert rejected == []
