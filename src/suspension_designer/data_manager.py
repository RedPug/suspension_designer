from uuid import uuid4
import json
import os
import csv

import numpy as np

from PySide6.QtWidgets import (
    QFileDialog,
)

FILE_FILTERS = {
    "proj": "Project Files (*.proj)",
    "csv": "CSV Files (*.csv)",
    "json": "JSON Files (*.json)"
}

def get_filepath(filepath: str=None, default_path: str = None, prompt: str = "Save As", filter: list[str] = ["proj", "csv"]) -> str:
    """Gathers a valid filepath, from a user dialog if necessary.

    Args:
        filepath (str, optional): Desired path to save to. Defaults to None.
        default_path (str, optional): Default path to use if the main filepath is invalid. Defaults to None.
        prompt (str, optional): Prompt for the file dialog. Defaults to "Save As".
        filter (list[str], optional): List of file filters. Defaults to ["proj", "csv"].

    Returns:
        str: A valid filepath or None.
    """
    if filepath is not None and os.path.exists(os.path.dirname(filepath)):
        print(f"Using existing filepath: {filepath}")
        return filepath
    
    if default_path is not None and os.path.exists(os.path.dirname(default_path)):
        print(f"Using default path: {default_path}")
        return default_path
    
    print("No valid filepath provided. Opening file dialog.")
    

    filepath, filter = QFileDialog.getSaveFileName(
        None,
        prompt,
        "",
        ";;".join(FILE_FILTERS.get(f, "") for f in filter),
    )

    if not filepath:
        return None
    
    return filepath
        

def save_json(filepath: str, data: dict) -> bool:
    """Saves the data to a specified JSON file

    Args:
        filepath (str): Filepath to save to. Can be absolute or relative.
        data (dict): Data to save, in a dictionary format. Can contain nested dict or list

    Returns:
        bool: True if successful, False otherwise
    """

    try:
        output_str = json.dumps(data, indent=2)

        with open(filepath, "w") as f:
            #only write to the file if there wasn't an error
            f.write(output_str)
    except Exception as e:
        print(f"Error occurred while serializing document data: {e}")
        return False

    return True

def save_csv(filepath: str, header: list[str], rows: list[list | dict]) -> bool:
    """Saves the data to a specified comma-separated-value file

    Args:
        filepath (str): Filepath to save to. Can be absolute or relative.
        header (list[str]): List of column names
        rows (list[list  |  dict]): list of rows, either as lists matching the header, or as dictionaries using the header as keys.

    Returns:
        bool: True if successful, False otherwise
    """
    assert header is not None, "Header cannot be None"
    assert rows is not None, "Rows cannot be None"
    assert isinstance(header, list), "Header must be a list"
    assert isinstance(rows, list), "Rows must be a list or dictionary"
    assert all(isinstance(row, (list, dict)) for row in rows), "All rows must be lists or dictionaries"
    if isinstance(rows[0], list):
        assert len(rows[0]) == len(header), "Row length must match header length"

    if isinstance(rows[0], dict):
        # only include the header keys when writing the csv.
        rows = [{header[i]: row[header[i]] for i in range(len(header))} for row in rows]

    try:
        with open(filepath, "w", newline="") as f:
            if isinstance(rows[0], dict):
                writer = csv.DictWriter(f, fieldnames=header)
                writer.writeheader()
                for row in rows:
                    writer.writerow(row)
            else:
                writer = csv.writer(f)
                writer.writerow(header)
                writer.writerows(rows)
    except Exception as e:
        print(f"Error occurred while serializing document data: {e}")
        return False

    return True