import argparse
import csv
import logging
import sys
from pathlib import Path
from typing import List
from uuid import NAMESPACE_URL, uuid5

# Ensure the backend package is importable when the script is executed directly
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.embedding_service import EmbeddingService
from vector_db.collections import KNOWLEDGEBASE_COLLECTION
from vector_db.payload_models import ServiceDocumentPayload

logger = logging.getLogger(__name__)


def _normalise_text(value: str) -> str:
    return value.strip()


def _parse_other_links(raw_links: str) -> List[str]:
    if not raw_links:
        return []
    segments = [segment.strip() for segment in raw_links.split(";")]
    return [segment for segment in segments if segment]


def _build_payload(row: dict) -> ServiceDocumentPayload:
    service_name = _normalise_text(row.get("Service Name", ""))
    if not service_name:
        raise ValueError("Missing service name in CSV row")

    service_link = _normalise_text(row.get("Service Link", ""))
    description = _normalise_text(row.get("Description", ""))
    mini_description = _normalise_text(row.get("Mini Description", ""))
    short_description = _normalise_text(row.get("Short Description", ""))
    other_links = _parse_other_links(row.get("Other Links", ""))
    date_value = _normalise_text(row.get("Date", ""))

    combined_parts = [
        service_name,
        description,
        mini_description,
        " ".join(other_links),
    ]
    combined_text = ". ".join(part for part in combined_parts if part)
    if not combined_text:
        combined_text = service_name

    record_namespace = f"{service_name}|{service_link or 'no-link'}"
    record_id = str(uuid5(NAMESPACE_URL, record_namespace))

    return ServiceDocumentPayload(
        record_id=record_id,
        service_name=service_name,
        description=description or None,
        mini_description=mini_description or None,
        short_description=short_description or None,
        service_link=service_link or None,
        other_links=other_links,
        combined_text=combined_text,
        date=date_value or None,
    )


def load_payloads(csv_path: Path) -> List[ServiceDocumentPayload]:
    logger.info("Loading CSV data from %s", csv_path)
    payloads: List[ServiceDocumentPayload] = []

    with csv_path.open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file, delimiter=";")
        for row_index, row in enumerate(reader, start=1):
            try:
                payloads.append(_build_payload(row))
            except ValueError as exc:
                logger.warning("Skipping row %s due to validation issue: %s", row_index, exc)

    logger.info("Prepared %s payloads for ingestion", len(payloads))
    return payloads


def ingest(csv_path: Path, batch_size: int) -> None:
    payloads = load_payloads(csv_path)
    if not payloads:
        logger.info("No payloads to ingest, exiting")
        return

    embedding_service = EmbeddingService()
    embedding_service.upsert_service_documents(payloads, batch_size=batch_size)
    logger.info(
        "Successfully ingested %s documents into collection '%s'",
        len(payloads),
        KNOWLEDGEBASE_COLLECTION,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest the Finnish services knowledge base into Qdrant.")
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path(BACKEND_ROOT.parent, "knowledgebase", "espoo_services.csv"),
        help="Path to the knowledge base CSV file.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Number of documents to embed per API request.",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    ingest(args.csv, args.batch_size)


if __name__ == "__main__":
    main()
