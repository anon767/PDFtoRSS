# Serve any PDF Book as RSS

I feel like sometimes I need to have my eBooks in byte-sized chunks.
This basically generates a RSS feed containing each chapter with a LLM generated summary as entry. 
It will also contain a link to a particular chapter that only shows these specific pages.

## Install

```
mkdir -p static/pdfs
pip3 install -r requirements.txt
python3 main.py
```

## Usage

Create a feed from a book async
http://127.0.0.1:5000/rss?url=urltopdf.pdf

Check task status
http://127.0.0.1:5000/task_status/<task_id>

Show a specific chapter
http://127.0.0.1:5000/pdf-chapter?file=20f529b89eba84b193cacb7591c07785.pdf&start_page=597&end_page=597

