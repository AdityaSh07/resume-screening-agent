from pathlib import Path
from uuid import uuid4

import pandas as pd
from langchain_community.document_loaders import CSVLoader
from langchain_core.documents import Document



ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}

#----------------------------- get csv -------------------------------
def load_candidates(file_path: str) -> list[Document]:

    path = Path(file_path)
    extension = path.suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type: {extension}. "
            "Only CSV and Excel files are allowed."
        )


    temp_csv_path = None

    try:
        if extension == ".csv":

            loader = CSVLoader(
                file_path=str(path), encoding="utf-8"
            )

            return loader.load()


        if extension in {".xlsx", ".xls"}:

            df = pd.read_excel(
                str(path)
            )

            temp_csv_path = path.parent / (
                f"converted_{uuid4().hex}.csv"
            )

            df.to_csv(
                temp_csv_path,
                index=False
            )

            loader = CSVLoader(
                file_path=str(temp_csv_path), encoding="utf-8"
            )

            documents = loader.load()

            return documents

    except pd.errors.EmptyDataError:
        raise ValueError(
            "The uploaded file is empty."
        )

    except pd.errors.ParserError:
        raise ValueError(
            "The CSV file could not be parsed."
        )

    except ValueError as e:
        raise e

    except Exception as e:
        print("ACTUAL ERROR:")
        print(type(e))
        print(repr(e))
        raise

    finally:

        if temp_csv_path and temp_csv_path.exists():

            try:
                temp_csv_path.unlink()

            except OSError:
                pass






