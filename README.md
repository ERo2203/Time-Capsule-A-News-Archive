# Time-Capsule-A-News-Archive

This repository contains a project for news archival and retrieval using a fine-tuned version of DistilBERT. The project consists of two major tasks: news archival and news retrieval, with the source code for each task provided in separate ZIP files.

## Project Overview

- **News Archival**: Organizing news articles from different providers in JSON format.
- **News Retrieval**: Using a fine-tuned DistilBERT model to retrieve relevant news articles based on user input.

## ZIP Files

The project is organized into two ZIP files, each handling one of the main tasks:

1. **Source Provider.zip**: Contains the code responsible for news archival from various sources.
2. **Context Provider.zip**: Contains the code and fine-tuned DistilBERT model for context-based news retrieval.

### Requirements

The required Python dependencies for this project are listed in the `requirements.txt` file. These need to be installed after setting up a virtual environment.

## Setup Instructions

### 1. Create a Virtual Environment
It is highly recommended to use a virtual environment to manage dependencies for this project. You can create and activate a virtual environment by following the steps below.

#### For MacOS/Linux:
```bash
# Install virtual environment if not installed
pip install virtualenv

# Create a virtual environment
virtualenv venv

# Activate the virtual environment
source venv/bin/activate
```

#### For Windows:
```bash
# Install virtual environment if not installed
pip install virtualenv

# Create a virtual environment
virtualenv venv

# Activate the virtual environment
venv\Scripts\activate
```

### 2. Install Dependencies

After activating your virtual environment, install the necessary packages listed in the `requirements.txt` file:

```bash
pip install -r requirements.txt
```

### 3. Unzip and Run the Project

#### a. News Archival (Source Provider.zip)
Unzip the **Source Provider.zip** file which contains the code for handling news archival from various providers. After running data.py and finetuned model:

```bash
# Example: Running the archival process
python app.py
```

#### b. News Retrieval (Context Provider.zip)
Unzip the **Retrieval Model.zip** file which contains the fine-tuned DistilBERT model and scripts for retrieving news articles.

```bash
# Example: Running the news retrieval process
python app.py
```

### Dataset

An example dataset (`myData.json`) is included in the project. It contains 32.3 MB of sample news data for testing purposes.

## Notes

- Make sure you are using Python 3.8 or higher for compatibility.
- If you want to fine-tune the DistilBERT model further, use the `train_model.py` script found inside **Retrieval Model.zip**.
- HTML templates (if used for web interface) can be found in the `templates/` directory inside the ZIP files.
