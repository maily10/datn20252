import sys
sys.path.append('.')
from content_crawler.factory import get_content_crawler

# Test baodautu.vn
url = 'https://baodautu.vn/chung-khoan-eurocapital-bi-xu-phat-d569930.html'
print('Testing URL:', url)
crawler = get_content_crawler(url)
print('Crawler object:', crawler)
if crawler:
    result = crawler.extract_article(url)
    if result:
        print('title:', result.get('title'))
        print('published_at:', result.get('published_at'))
        print('summary:', result.get('summary')[:100] if result.get('summary') else '')
        print('content length:', len(result.get('content', '')))
        print('image_url:', result.get('image_url'))
    else:
        print('RESULT IS NONE - extract_article returned None')
else:
    print('NO CRAWLER FOUND for domain!')
