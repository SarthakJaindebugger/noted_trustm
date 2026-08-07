import os
from fastapi import UploadFile
import aiofiles
import logging

logger = logging.getLogger(__name__)

async def save_upload_file(upload_file: UploadFile, destination_dir: str) -> str:
    """
    Saves an uploaded file to a destination directory using its original name.

    If a file with the same name already exists, a numeric suffix is appended
    (e.g. recording_2.wav, recording_3.wav).

    Args:
        upload_file: The file uploaded via a FastAPI endpoint.
        destination_dir: The directory where the file should be saved.

    Returns:
        The full path to the saved file.
    """
    try:
        original_filename = upload_file.filename
        safe_filename = "".join(c for c in original_filename if c.isalnum() or c in ('.', '_', '-')).strip()
        filename_base, file_extension = os.path.splitext(safe_filename)

        filepath = os.path.join(destination_dir, f"{filename_base}{file_extension}")

        # If file already exists, append a numeric suffix
        counter = 2
        while os.path.exists(filepath):
            filepath = os.path.join(destination_dir, f"{filename_base}_{counter}{file_extension}")
            counter += 1

        # Asynchronously write the file in chunks
        async with aiofiles.open(filepath, 'wb') as out_file:
            while content := await upload_file.read(1024 * 1024):  # Read in 1MB chunks
                await out_file.write(content)

        return filepath
    except Exception as e:
        logger.error(f"Could not save file {upload_file.filename}: {e}")
        raise