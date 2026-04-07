class WebSearchEngine:
    @staticmethod
    def search_duckduckgo(query, max_results=5):
        try:
            try:
                from duckduckgo_search import DDGS
                results = []
                # ✅ API ANTIGUA (duckduckgo-search 3.9.10)
                ddgs = DDGS()
                search_results = ddgs.text(query, max_results=max_results)
                
                for result in search_results:
                    results.append({
                        'title': result.get('title'),
                        'url': result.get('href'),
                        'snippet': result.get('body'),
                        'source': 'duckduckgo'
                    })
                return results
            except ImportError:
                logger.warning("duckduckgo-search no instalada, usando fallback")
                return WebSearchEngine._search_fallback(query, max_results)
        except Exception as e:
            logger.error(f"Error en búsqueda DuckDuckGo: {e}")
            return []
    
    @staticmethod
    def _search_fallback(query, max_results=5):
        try:
            url = f"https://html.duckduckgo.com/?q={urllib.parse.quote(query)}"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            results = []
            for result in soup.find_all('div', class_='result')[:max_results]:
                try:
                    title_elem = result.find('a', class_='result__a')
                    snippet_elem = result.find('a', class_='result__snippet')
                    if title_elem and snippet_elem:
                        results.append({
                            'title': title_elem.get_text(),
                            'url': title_elem.get('href', ''),
                            'snippet': snippet_elem.get_text(),
                            'source': 'duckduckgo'
                        })
                except:
                    continue
            return results
        except Exception as e:
            logger.error(f"Error en fallback de búsqueda: {e}")
            return []
