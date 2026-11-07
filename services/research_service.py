import requests
import xml.etree.ElementTree as ET
import urllib.parse

def search_arxiv(query, max_results=10):
    try:
        # Clean and encode the query
        encoded_query = urllib.parse.quote(query.strip())
        
        # Call the arXiv API
        url = f"http://export.arxiv.org/api/query?search_query=all:{encoded_query}&start=0&max_results={max_results}&sortBy=relevance"
        
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        
        # Parse the XML response
        root = ET.fromstring(response.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        
        papers = []
        for entry in root.findall("atom:entry", ns):
            title = entry.find("atom:title", ns).text.strip().replace("\n", " ")
            summary = entry.find("atom:summary", ns).text.strip().replace("\n", " ")
            link = entry.find("atom:id", ns).text.strip()
            published = entry.find("atom:published", ns).text[:10]
            
            # Extract authors
            authors = []
            for author in entry.findall("atom:author", ns):
                name = author.find("atom:name", ns).text
                authors.append(name)
            
            papers.append({
                "title": title,
                "summary": summary,
                "link": link,
                "published": published,
                "authors": ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else "")
            })
            
        return papers
    except Exception as e:
        print(f"❌ arXiv API Error: {e}")
        return []