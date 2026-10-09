"""Seeds the catalog with example pieces and a GENERIC size table.

Run: PYTHONPATH=src uv run python scripts/seed.py

The measurements below are illustrative placeholders — replace them with the
real measurements of your pieces and your own size table. Idempotent: pieces
are skipped when the SKU exists; the size table is only seeded when empty.
"""

from catalog import repository
from catalog.db import session_scope
from catalog.schemas import ItemCreate, Measurements, SizeEquivalenceIn
from config.envs import envs
from config.logging import get_logger, setup_logging

setup_logging(level=envs.log_level)
logger = get_logger(__name__)


ITEMS = [
    ItemCreate(
        sku="RT-0001",
        title="Calça jeans Levi's 501 cintura alta",
        description="Jeans azul médio lavado, cintura alta, perna reta. Etiqueta original.",
        category="calça",
        department="feminino",
        brand="Levi's",
        era="anos 90",
        label_size="40",
        color="azul médio",
        fabric="jeans 100% algodão",
        stretch="none",
        style_tags=["vintage", "casual", "anos 90"],
        occasions=["dia a dia", "passeio", "trabalho casual"],
        condition="ótimo estado",
        price=189.90,
        measurements=Measurements(waist=76, hip=100, rise=31, inseam=76, thigh=60, hem=38, length=104),
    ),
    ItemCreate(
        sku="RT-0002",
        title="Jaqueta de couro preta estilo perfecto",
        description="Couro legítimo, zíperes prateados, forro em cetim.",
        category="jaqueta",
        department="unissex",
        era="anos 80",
        label_size="M",
        color="preto",
        fabric="couro",
        stretch="none",
        style_tags=["rock", "vintage", "urbano"],
        occasions=["noite", "show", "dia a dia"],
        condition="bom, com marcas de uso",
        price=349.00,
        measurements=Measurements(chest=104, shoulder=44, sleeve=62, length=58),
    ),
    ItemCreate(
        sku="RT-0003",
        title="Camisa de seda off-white",
        description="Camisa fluida de seda, gola clássica, botões de madrepérola.",
        category="camisa",
        department="feminino",
        era="anos 90",
        label_size="P",
        color="off-white",
        fabric="seda",
        stretch="none",
        style_tags=["minimalista", "clássico", "elegante"],
        occasions=["trabalho", "jantar", "evento diurno"],
        condition="ótimo estado",
        price=159.00,
        measurements=Measurements(chest=96, shoulder=39, sleeve=58, length=66),
    ),
    ItemCreate(
        sku="RT-0004",
        title="Blusa de tricô listrada vermelho e creme",
        description="Tricô macio, listras horizontais, gola careca.",
        category="blusa",
        department="feminino",
        color="vermelho e creme",
        fabric="tricô de algodão",
        stretch="medium",
        style_tags=["casual", "francês", "retrô"],
        occasions=["dia a dia", "passeio", "fim de semana"],
        condition="ótimo estado",
        price=89.00,
        measurements=Measurements(chest=92, length=58),
    ),
    ItemCreate(
        sku="RT-0005",
        title="Cinto de couro caramelo com fivela dourada",
        description="Couro marrom caramelo, fivela dourada oval.",
        category="acessório",
        department="unissex",
        color="caramelo",
        fabric="couro",
        style_tags=["vintage", "western", "clássico"],
        occasions=["dia a dia", "trabalho casual"],
        condition="bom estado",
        price=59.00,
        measurements=Measurements(length=98),
    ),
]


# Generic BR women's pants table (approximate). Brand/era rows win over it.
def _pants(size: str, waist: tuple[float, float], hip: tuple[float, float]) -> SizeEquivalenceIn:
    return SizeEquivalenceIn(
        category="calça",
        label_size=size,
        department="feminino",
        measurements={"waist": waist, "hip": hip},
        notes="Tabela genérica aproximada — substitua pela sua.",
    )


SIZE_TABLE = [
    _pants("36", (66, 70), (92, 96)),
    _pants("38", (70, 74), (96, 100)),
    _pants("40", (74, 78), (100, 104)),
    _pants("42", (78, 82), (104, 108)),
    _pants("44", (82, 86), (108, 112)),
    _pants("46", (86, 90), (112, 116)),
    # Example of a brand + era specific row: old 501s run small.
    SizeEquivalenceIn(
        category="calça",
        label_size="40",
        department="feminino",
        brand="Levi's",
        era="anos 90",
        measurements={"waist": (72, 76), "hip": (98, 102)},
        notes="Exemplo: 501 anos 90 veste ~1 número menor que a tabela atual.",
    ),
]


def main() -> None:
    with session_scope() as session:
        for data in ITEMS:
            if repository.get_item(session, data.sku):
                logger.info(f"Skipping {data.sku} (already exists)")
                continue
            item = repository.create_item(session, data)
            logger.info(
                f"Created {data.sku}: {item.title} (embedding={'ok' if item.embedding is not None else 'missing'})"
            )

        if repository.list_size_equivalences(session):
            logger.info("Size table already has rows — skipping.")
        else:
            for row in SIZE_TABLE:
                repository.create_size_equivalence(session, row)
            logger.info(f"Seeded {len(SIZE_TABLE)} size equivalence rows.")


if __name__ == "__main__":
    main()
