# Server any PDF Book as RSS

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

To get the RSS feed:
http://127.0.0.1:5000/rss?url=urltopdf.pdf


