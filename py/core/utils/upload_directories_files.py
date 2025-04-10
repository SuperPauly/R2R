import logging
import os
from pathlib import Path, PurePath
from uuid import UUID

from r2r import R2RClient
from shared.abstractions import DocumentType

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def scan_directory(
    root_dir,
    ignore_dirs=None,
    accepted_exts=None,
    ignore_exts=None,
    include_file_at_specific_path=None,
    ignore_filenames=None,
    ignore_file_paths=None,
) -> list[str] | None:
    """
    Recursively scan a directory and filter files based on various criteria.

    Args:
        root_dir: Directory path to scan
        ignore_dirs: List of directory names to ignore
        accepted_exts: List of file extensions to include (e.g., [".py", ".txt"])
        ignore_exts: List of file extensions to exclude
        include_file_at_specific_path: List of filenames to include even in ignored dirs
        ignore_filenames: List of filenames to ignore
        ignore_file_paths: List of relative file paths to ignore

    Returns:
        list[str] or None: A list of file paths that match the criteria, None if no matches
    """
    # Check if root_dir is a valid path
    try:
        if root_dir is None:
            raise ValueError(
                "Invalid root_dir: None. Root directory cannot be None."
            )
        if PurePath(root_dir):
            pass
    except (AttributeError, TypeError) as e:
        # Add "from e" to properly chain exceptions
        raise ValueError(
            f"Invalid root_dir: {root_dir}. Error: {e}. Does root_dir exist?"
        ) from e

    # Set default values for parameters
    ignore_dirs = ignore_dirs or [
        "__pycache__",
        ".vscode",
        ".github",
        "venv",
        ".venv",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
    ]

    # Handle accepted extensions
    if accepted_exts is None:
        # Get file extensions from DocumentType enum
        accepted_exts = []
        for doc_type in DocumentType:
            accepted_exts.append(f".{doc_type.value.lower()}")

    ignore_exts = ignore_exts or []
    include_file_at_specific_path = include_file_at_specific_path or []
    ignore_filenames = ignore_filenames or []
    ignore_file_paths = ignore_file_paths or []

    # Begin scanning
    matched_files = []

    # Normalize the ignore file paths for consistent comparison
    normalized_ignore_paths = [
        os.path.normpath(ignore) for ignore in ignore_file_paths
    ]

    # Special case: If include_file_at_specific_path is specified, we need to do a full scan first
    if include_file_at_specific_path:
        # Do a full scan to find special files, even in ignored directories
        for root, _, files in os.walk(root_dir):
            for filename in files:
                if filename in include_file_at_specific_path:
                    file_path = os.path.join(root, filename)
                    matched_files.append(file_path)

    # Regular scan with directory filtering
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Skip directories in the ignore list
        dirnames[:] = [d for d in dirnames if d not in ignore_dirs]

        for filename in filenames:
            # Skip files with ignored filenames
            if filename in ignore_filenames:
                continue

            file_path = os.path.join(dirpath, filename)

            # Compute the relative path and normalize it
            rel_path = os.path.normpath(os.path.relpath(file_path, root_dir))

            # If this relative path is in the ignore list, skip this file
            if rel_path in normalized_ignore_paths:
                continue

            # Check if file should be excluded based on extension
            if any(
                filename.lower().endswith(ext.lower()) for ext in ignore_exts
            ):
                continue

            # Include file if it meets either extension or name criteria
            ext_match = any(
                filename.lower().endswith(ext.lower()) for ext in accepted_exts
            )
            name_match = filename in include_file_at_specific_path

            # If no filters are provided, include all files
            include_all = not (accepted_exts or include_file_at_specific_path)

            if include_all or ext_match or name_match:
                # Don't add duplicates from the special scan
                if file_path not in matched_files:
                    matched_files.append(file_path)

    if matched_files == []:
        return None
    else:
        return matched_files


def insert_files_into_r2r(
    client: R2RClient,
    file_paths: list[str],
    metadata: dict,
    collection_id: list[str | UUID],
    collection_name: str = "default",
    create_new_collection: bool = False,
    collection_description: str = "",
    login_email: str = "",
    login_password: str = "",
    extract_document: bool = False,
    ingestion_mode: str = "fast",
):
    """
    Inserts files into R2R using the R2RClient.

    Args:
        client: R2RClient instance.
        file_paths: List of file paths to insert.
        collection_id: Existing collection ID (optional).
        create_new_collection: Create a new collection if True (optional).
        login_email: Str of the 'email' for login (optional).
        login_password: StrUUID of the 'password' for login (optional).
        extract_document: Extract entities and relationships after insertion if True (optional).
        extraction_document: Mode for extraction, either "fast" or "hi-res" (optional).
        metadata: Metadata to attach to the document (optional).
    """

    if login_email and login_password:
        try:
            login_response = client.users.login(login_email, login_password)
            logger.info(f"Login successful for user: {login_email}")
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return

    if create_new_collection and collection_name is not None:
        try:
            create_collection_response = client.collections.create(
                name=collection_name, description=collection_description
            )
            cNoneollection_id = create_collection_response.results.id
            logger.info(f"New collection created with ID: {collection_id}")
        except Exception as e:
            logger.error(f"Failed to create new collection: {e}")
            return

    if not collection_id:
        logger.warning(
            "No collection ID provided.  Files will be added to the default collection."
        )
    for file_path in file_paths:
        file_name = os.path.basename(file_path)
        # Search for the document by name
        try:
            metadata["file_path"] = file_path
            search_response = client.retrieval.search(
                query=file_name,
                search_settings={
                    "use_semantic_search": False,
                    "use_fulltext_search": True,
                    "filters": {"collection_id": {"$eq": collection_id}}
                    if collection_id
                    else [],
                },
            )

            # Check if any results were found
            if search_response.results.chunk_search_results != []:
                logger.info(
                    f"Document '{file_name}' already exists in R2R. Skipping."
                )
                continue  # Skip to the next file
        except Exception as e:
            logger.error(f"Error during search for '{file_name}': {e}")
            continue  # Skip to the next file

        try:
            ingest_response = client.documents.create(
                file_path=file_path,
                collection_ids=collection_id if collection_id else None,
                metadata=metadata,
                ingestion_mode=ingestion_mode,
            )
            document_id = ingest_response.results.document_id
            logger.info(
                f"File '{file_path}' ingested successfully. Document ID: {document_id}"
            )

            if extract_document:
                try:
                    extract_response = client.documents.extract(document_id)
                    logger.info(
                        f"Entities and relationships extracted for document ID: {document_id}"
                    )
                    logger.info(
                        f"Extracted entities: {extract_response.results}"
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to extract entities and relationships for document ID {document_id}: {e}"
                    )

        except Exception as e:
            logger.error(f"Failed to ingest file '{file_path}': {e}")


if __name__ == "__main__":
    client = R2RClient("http://localhost:7272")
    root_directory = f"{Path(__file__).parent.parent.parent}"

    scan_results = scan_directory(root_directory)
    results = scan_results if scan_results is not None else []

    insert_files_into_r2r(
        client=client,
        file_paths=results,
        collection_id=["ae005dab-b2b1-49cf-bf81-83bb2f3f4feb"],
        metadata={"source": "local"},
    )
