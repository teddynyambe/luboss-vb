"""Proof-of-payment files on a DepositProof.

A declaration has one live DepositProof (one approval, one journal entry),
but the member may have paid it in several deposits — so a proof can carry
several files. The first lives on `DepositProof.upload_path` (which may be
the "reconciliation" placeholder when the treasurer posted without a slip);
any further ones are `DepositProofFile` rows.
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import DEPOSIT_PROOFS_DIR
from app.models.transaction import DepositProof, DepositProofFile

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".gif"}
MAX_FILES_PER_PROOF = 10
RECONCILIATION_PLACEHOLDER = "reconciliation"


def validate_proof_upload(file: UploadFile) -> None:
    """Raise ValueError unless the upload is a PDF or image."""
    ext = Path(file.filename).suffix.lower() if file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Invalid file type. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")


def save_proof_upload(file: UploadFile, stub) -> Path:
    """Write an uploaded proof to DEPOSIT_PROOFS_DIR and return its path.

    Same naming pattern as the original single-file upload so the existing
    file-serving endpoint works unchanged. Microseconds keep several files
    saved in one request from colliding.
    """
    validate_proof_upload(file)
    DEPOSIT_PROOFS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    safe_filename = (
        "".join(c for c in file.filename if c.isalnum() or c in "._- ")
        if file.filename else "proof"
    )
    file_path = DEPOSIT_PROOFS_DIR / f"deposit_{stub}_{timestamp}_{safe_filename}"
    with open(file_path, "wb") as f:
        f.write(file.file.read())
    return file_path


def _unlink(path: str | None) -> None:
    """Best-effort removal of a stored proof file."""
    if not path or path == RECONCILIATION_PLACEHOLDER:
        return
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


def has_main_file(deposit: DepositProof) -> bool:
    return bool(deposit.upload_path and deposit.upload_path != RECONCILIATION_PLACEHOLDER)


def proof_files_payload(deposit: DepositProof) -> list[dict]:
    """Every real file on the proof, main file first, for API responses."""
    files: list[dict] = []
    if has_main_file(deposit):
        files.append({
            "id": "main",
            "upload_path": deposit.upload_path,
            "filename": Path(deposit.upload_path).name,
            "uploaded_at": deposit.uploaded_at.isoformat() if deposit.uploaded_at else None,
            "is_main": True,
        })
    for f in deposit.extra_files:
        files.append({
            "id": str(f.id),
            "upload_path": f.upload_path,
            "filename": Path(f.upload_path).name,
            "uploaded_at": f.uploaded_at.isoformat() if f.uploaded_at else None,
            "is_main": False,
        })
    return files


def add_proof_file(
    db: Session, deposit: DepositProof, file: UploadFile, user_id: UUID | None
) -> dict:
    """Attach one more file to the proof. Does not change status or commit.

    When the proof has no real main file yet (reconciliation placeholder),
    the upload becomes the main file instead of an extra.
    """
    if len(proof_files_payload(deposit)) >= MAX_FILES_PER_PROOF:
        raise ValueError(f"A proof can hold at most {MAX_FILES_PER_PROOF} files.")
    file_path = save_proof_upload(file, deposit.declaration_id or deposit.id)
    if not has_main_file(deposit):
        deposit.upload_path = str(file_path)
        return {"id": "main", "filename": file_path.name, "is_main": True}
    row = DepositProofFile(
        deposit_proof_id=deposit.id,
        upload_path=str(file_path),
        uploaded_by=user_id,
    )
    deposit.extra_files.append(row)
    db.flush()
    return {"id": str(row.id), "filename": file_path.name, "is_main": False}


def remove_extra_file(db: Session, deposit: DepositProof, file_id: UUID) -> str:
    """Delete one additional file (row + disk). Returns its filename.
    The main file can only be replaced, not removed. Does not commit."""
    row = next((f for f in deposit.extra_files if f.id == file_id), None)
    if row is None:
        raise ValueError("Proof file not found.")
    name = Path(row.upload_path).name
    _unlink(row.upload_path)
    deposit.extra_files.remove(row)
    db.flush()
    return name


def delete_extra_files(db: Session, deposit: DepositProof) -> None:
    """Drop every additional file (rows + disk). Used wherever the main
    file is discarded along with the proof. Does not commit."""
    for row in list(deposit.extra_files):
        _unlink(row.upload_path)
        deposit.extra_files.remove(row)
    db.flush()
