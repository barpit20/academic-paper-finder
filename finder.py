import requests
from urllib import parse
import re
import pandas as pd
import json
import os
import io
import helpers as h
import math
import time
import progressbar
import sys
import PyPDF2
import warnings

class Fetcher:
    def __init__(self, search_parameters={}, load_from='cache', **kwargs):
        self.load_from = load_from
        self.name = kwargs.get('name', 'finder')
        self.cache_folder = kwargs.get('cache_folder', './cache')
        self.headers = kwargs.get('headers', {})
        
        self.per_page = kwargs.get('per_page', 500)

        self.search_parameters = search_parameters
        self.config_name = kwargs.get('config_name', self.name)
        
        config_path = "./configs/%s.json" % self.config_name
        with open(config_path, "r") as f:
            self.config = json.load(f)
        
        self.list_is_json = self.get_config('urls.list.expect-json', False)
        self.paper_is_json = self.get_config('urls.paper.expect-json', False)
        self.per_page = self.get_config('urls.list.per-page')

        self.restrict_identifiers_to = kwargs.get('restrict_identifiers_to', [])

    @property
    def header_user_agent(self):
        return 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/84.0.4147.89 Safari/537.36'

    def list_file_name(self, page):
        return "%s/%s/list/%s/%s.html" % (self.cache_folder, self.config_name, self.name, 'page-%d' % page)

    def paper_file_name(self, identifier):
        safe_identifier = h.safe_filename(identifier)
        return "%s/%s/papers/%s.html" % (self.cache_folder, self.config_name, safe_identifier)
    
    def pdf_file_name(self, identifier):
        safe_identifier = h.safe_filename(identifier)
        return "%s/%s/pdfs/%s.pdf" % (self.cache_folder, self.config_name, safe_identifier)

    def result_file_name(self):
        return "%s/%s/result_%s.json" % (self.cache_folder, self.config_name, self.name)

    def url_get(self, url, payload={}, headers={}):
        headers = { 'user-agent': self.header_user_agent, **headers }
        return requests.get(h.url_base_with_path(url), headers=headers, params=payload)

    def url_post_json(self, url, payload={}, headers={}):
        headers = { 
            'user-agent': self.header_user_agent,
            'accept': '*/*',
            'content-type': 'application/json',
            **self.headers,
            **headers
        }
        return requests.post(h.url_base_with_path(url), headers=headers, data=json.dumps(payload))

    def url_post(self, url, payload={}, headers={}):
        headers = {
            'user-agent': self.header_user_agent,
            'accept': '*/*',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            **self.headers,
            **headers
        }
        return requests.post(h.url_base_with_path(url), headers=headers, data=payload)

    def ensure_cache_folder_exists(self):
        if not h.check_file_exists(self.cache_folder):
            os.mkdir(self.cache_folder)

    def paper_file_exists(self, identifier):
        return h.check_file_exists(self.paper_file_name(identifier))

    def pdf_file_exists(self, identifier):
        return h.check_file_exists(self.pdf_file_name(identifier))

    def list_file_exists(self, page):
        return h.check_file_exists(self.list_file_name(page))

    def fetch_list(self, page):
        if (self.load_from == 'cache'):
            if(self.list_file_exists(page)): return self.from_cache(self.list_file_name(page), self.list_is_json)
            else: return self.from_url_list(page)
        elif (self.load_from == 'url'): return self.from_url_list(page)
        else: raise Exception("load_from could not be found")

    def fetch_paper(self, identifier):
        if (self.load_from == 'cache'):
            if(self.paper_file_exists(identifier)): return self.from_cache(self.paper_file_name(identifier), self.paper_is_json)
            else: return self.from_url_paper(identifier)
        elif (self.load_from == 'url'): return self.from_url_paper(identifier)
        else: raise Exception("load_from could not be found")

    def fetch_pdf(self, identifier):
        if (self.load_from == 'cache'):
            if(self.pdf_file_exists(identifier)): 
                with open(self.pdf_file_name(identifier), "rb") as f: return f.read()
            else: return self.from_url_pdf(identifier)
        elif (self.load_from == 'url'): return self.from_url_pdf(identifier)
        else: raise Exception("load_from could not be found")

    def from_cache(self, path, is_json):
        html = h.read_file(path)
        should_not_be_decoded = not is_json or isinstance(html, dict)
        return html if should_not_be_decoded else json.loads(html)
    
    def from_url_pdf(self, identifier):
        sleep_for = self.get_config('sleep_between_requests')
        r = requests.get(self.pdf_url(identifier))
        file_name = self.pdf_file_name(identifier)
        h.ensure_path_exists(file_name)
        with open(file_name, "wb") as f: f.write(r.content)
        time.sleep(sleep_for)
        return r.content

    def from_url_list(self, page):
        sleep_for = self.get_config('sleep_between_requests')
        html = self.fetch_list_from_url(page)
        h.write_file(self.list_file_name(page), html)
        shouldNotBeDecoded = not self.list_is_json or isinstance(html, dict)
        time.sleep(sleep_for)
        return html if shouldNotBeDecoded else json.loads(html)

    def from_url_paper(self, identifier):
        sleep_for = self.get_config('sleep_between_requests')
        html = self.fetch_paper_from_url(identifier)
        h.write_file(self.paper_file_name(identifier), html)
        shouldNotBeDecoded = not self.paper_is_json or isinstance(html, dict)
        time.sleep(sleep_for)
        return html if shouldNotBeDecoded else json.loads(html)
    
    def re_list(self, pattern, html):
        if len(pattern) == '': return []
        return h.unique(map(
            lambda s: h.strip_html(s).replace("\n", " ").strip(),
            re.findall(pattern, html)
        ))
    
    def re_item(self, pattern, html):
        if len(pattern) == '': return ''
        find = re.findall(pattern, html)
        if len(find) <= 0: return ''
        f = find[0] if not isinstance(find[0], tuple) else find[0][0]
        return h.strip_html(f).replace("\n", " ").strip()

    def get_config(self, field, default=''):
        try: return h.get_dict_field(self.config, field)
        except ValueError: return default

    def list_url(self, page):
        return h.insert_identifier(self.get_config("urls.list.url"), page, "page")
    
    def paper_url(self, identifier):
        return h.insert_identifier(self.get_config("urls.paper.url"), identifier)

    def pdf_url(self, identifier):
        return h.insert_identifier(self.get_config("urls.pdf"), identifier)

    def identifiers(self, _list):
        if self.list_is_json:
            return h.get_dict_field(_list, self.get_config('json.list.identifiers'))
        else:
            pattern = self.get_config("regex.list.identifiers")
            return self.re_list(pattern, _list)
    
    def total_number_of_results(self, _list):
        if self.list_is_json:
            scount = h.get_dict_field(_list, self.get_config('json.list.total_number_of_results'))
        else:
            pattern = self.get_config("regex.list.total_number_of_results")
            scount = self.re_item(pattern, _list)
            scount = scount.replace(',', '')
        try: count = int(scount)
        except ValueError: count = 0
        return count

    def fetch_list_from_url(self, page):
        payload = self.search_parameters

        per_page_param = self.get_config("urls.list.params.per-page", "")
        if not per_page_param == "": payload[per_page_param] = self.per_page
        
        page_param = self.get_config("urls.list.params.page", "")
        if not page_param == "":
            if self.get_config("urls.list.params.offset", False):
                page = page * payload[per_page_param]
            payload[page_param] = page

        method = self.get_config("urls.list.method", "GET")
        url = self.list_url(page)
        if method == "GET":
            return self.url_get(url, payload).text
        elif method == "POST" and not self.get_config('urls.list.send-json', False):
            return self.url_post(url, payload).text
        else:
            return self.url_post_json(url, payload).json()

    def fetch_paper_from_url(self, identifier):
        method = self.get_config("urls.paper.method", "GET")
        if method == "GET":
            return self.url_get(self.paper_url(identifier)).text
        elif method == "POST" and not self.list_is_json:
            return self.url_post(self.paper_url(identifier)).text
        else:
            return self.url_post_json(self.paper_url(identifier)).json()

    def from_paper(self, key, _paper, item=True, default=''):
        fun = self.re_item if item else self.re_list
        is_pre_json = 'embedded_json' in self.get_config("preprocessing.paper.*.type", [])
        return fun(self.get_config("regex.paper.%s" % key, default=default), _paper) \
            if not is_pre_json else \
            h.get_dict_field(_paper, self.get_config("json.paper.%s" % key), '')

    def authors(self, _paper):
        return list(map(lambda s: s.title(), h.flatten(self.from_paper("authors", _paper, False))))

    def keywords(self, _paper):
        return h.flatten(self.from_paper("keywords", _paper, False))

    def title(self, _paper):
        return self.from_paper("title", _paper)

    def abstract(self, _paper):
        return self.from_paper("abstract", _paper)

    def publication_date(self, _paper):
        return self.from_paper("publication_date", _paper)

    def published_in(self, _paper):
        return self.from_paper("published_in", _paper)

    def citations(self, _paper):
        return self.from_paper("citations", _paper)

    def isbn(self, _paper):
        return self.from_paper("isbn", _paper)

    def doi(self, _paper):
        return self.from_paper("doi", _paper)

    def preprocess_paper(self, _paper):
        preprocessing = self.get_config("preprocessing.paper", [])
        if len(preprocessing) > 0:
            for pre in preprocessing:
                if pre["type"] == "embedded_json":
                    raw_paper = self.re_item(pre['regex'], _paper)
                    _paper = json.loads(raw_paper)
        return _paper
    
    def preprocess_list(self, _list):
        preprocessing = self.get_config("preprocessing.list", [])
        if len(preprocessing) > 0:
            for _ in preprocessing:
                pass
        return _list

    def postprocess_paper(self, paper):
        postprocessing = self.get_config("postprocessing.paper", [])
        if len(postprocessing) > 0:
            for i, post in enumerate(postprocessing):
                if post["type"] == "query":
                    f = h.analyze_query(paper, self.get_config(f"postprocessing.paper.{i}.query", {}))
                    paper = paper if f else None
        return paper

    def parse_paper(self, identifier, _paper):
        _paper = self.preprocess_paper(_paper)
        paper = {
            'title': self.title(_paper),
            'authors': self.authors(_paper),
            'abstract': self.abstract(_paper),
            'keywords': self.keywords(_paper),
            'published_in': self.published_in(_paper),
            'publication_date': self.publication_date(_paper),
            'citations': self.citations(_paper),
            'isbn': self.isbn(_paper),
            'doi': self.doi(_paper),

            'pdf_url': self.pdf_url(identifier),
            'paper_url': self.paper_url(identifier),
            'identifier': identifier
        }
        paper = self.postprocess_paper(paper)
        return paper

    def fetch_parse_papers(self, identifiers):
        sub = h.get_progressbar(len(identifiers))
        sub.start()
        papers = []
        for i, identifier in enumerate(identifiers):
            sub.update(i)
            if len(self.restrict_identifiers_to) > 0 and identifier not in self.restrict_identifiers_to: continue
            _paper = self.fetch_paper(identifier)
            paper = self.parse_paper(identifier, _paper)
            if paper is not None:
                papers.append(paper)
        sub.finish()
        return papers

    def fetch_parse_list(self, page):
        _list = self.fetch_list(page)
        identifiers = self.identifiers(_list)
        return _list, self.fetch_parse_papers(identifiers)

    def run(self):
        tic = time.perf_counter()
        print("", "---------------", "starting on %s - %s" % (self.config_name, self.name), sep="\n")
        
        print(" - fetching first page")
        start_page = self.get_config('urls.list.start-page', 0)
        _list, papers = self.fetch_parse_list(start_page)
        result = { 
            'papers': [papers],
            'total_results': self.total_number_of_results(_list)
        }
        
        pages_to_fetch = math.ceil(result['total_results'] / self.per_page) - 1

        sleep_for = self.get_config('sleep_between_requests')
        print("This will take at least %.2f hours if the cache is clean" % ((result['total_results'] * sleep_for) / 60 / 60))

        if ((pages_to_fetch) > 0):
            print(" - fetching the rest of the pages: %d" % (pages_to_fetch))
            
            h.console_down()
            total = h.get_progressbar(pages_to_fetch, 'lists')
            total.start()
            for i, page in enumerate(range(start_page + 1, pages_to_fetch + start_page + 1)):
                total.update(i)
                # if page >= 2: break
                h.console_up()
                _, papers = self.fetch_parse_list(page)
                result['papers'].append(papers)
            total.finish()
        
        result['papers'] = h.flatten(result['papers'])
        result['total_filtered_results'] = len(result['papers'])
        result['total_pages'] = pages_to_fetch + 1
        h.write_json_file(self.result_file_name(), result)
        toc = time.perf_counter()
        h.console_down()
        print(f"Finished {self.config_name} - {self.name} in {toc - tic:0.4f} seconds\n")
        return result

    def export_results_to_csv(self, fields=[], file_path='./total.csv', override=False, defaults={}, sort_by=None):
        result = h.read_json_file(self.result_file_name())
        if not 'papers' in result: raise Exception("Illformed %s" % self.result_file_name())
        if len(result['papers']) <= 0: return
        if len(fields) <= 0: fields = list(result['papers'][0].keys())

        if h.check_file_exists(file_path) and not override:
            df = pd.read_csv(file_path)
        else:
            df = pd.DataFrame(columns=fields)
        
        print(f"Exporting {self.name} - {self.config_name} paper to csv.")
        total = h.get_progressbar(len(result['papers']), 'pdf')
        total.start()
        for i, paper in enumerate(result['papers']):
            if len(self.restrict_identifiers_to) > 0 and paper['identifier'] not in self.restrict_identifiers_to: continue
            paper_dict = {
                k: ( paper[k] if not isinstance(paper[k], list) else ", ".join(paper[k]) ) 
                    if k in paper else
                    ( defaults[k] if k in paper else None )
                for k 
                in fields
            }
            df = df.append(paper_dict, ignore_index=True)
            total.update(i)
        total.finish()

        if sort_by is not None:
            if not isinstance(sort_by, list):
                sort_by = [sort_by]
            
            if all(map(lambda x: x in fields, sort_by)):
                df.sort_values(by=sort_by)
            else:
                warnings.warn(f"could not find sorting field: {str(sort_by)} is not completely in {str(fields)}")

        df.to_csv(file_path, index=False)

    def download_pdfs(self, save_folder='./pdfs', save_name="identifier", override=False):
        result = h.read_json_file(self.result_file_name())
        if not 'papers' in result: raise Exception("Illformed %s" % self.result_file_name())
        if len(result['papers']) <= 0: return

        save_folder = f"{save_folder}"
        h.ensure_path_exists(save_folder, True)
        
        sleep_for = self.get_config('sleep_between_requests')

        print(f"Downloading {self.name} - {self.config_name} paper pdfs.")
        sleep_for = self.get_config('sleep_between_requests')
        print("This will take at least %.2f hours if all papers need to be downloaded" % ((result['total_results'] * sleep_for) / 60 / 60))

        total = h.get_progressbar(len(result['papers']), 'pdf')
        total.start()
        for i, paper in enumerate(result['papers']):
            total.update(i)
            if len(self.restrict_identifiers_to) > 0 and paper['identifier'] not in self.restrict_identifiers_to: continue
            
            num_pages_key = 'pdf_num_pages'
            if num_pages_key in paper and not override: continue

            file_name = h.safe_filename(f"{paper['identifier']}.pdf")
            file_name = f"{save_folder}/{file_name}"
            
            content = self.fetch_pdf(paper['identifier'])
            with open(file_name, "wb") as f: f.write(content)

            try:
                pdf_file = io.BytesIO(content)
                pdf_reader = PyPDF2.PdfFileReader(pdf_file)
                paper[num_pages_key] = pdf_reader.getNumPages()
                result['papers'][i] = paper
            except PyPDF2.utils.PdfReadError:
                os.remove(self.pdf_file_name(paper['identifier']))
                h.console_down()
                print(f"Reading PDF failed: id {paper['identifier']}")
            
        total.finish()
        h.write_json_file(self.result_file_name(), result)

if __name__ == "__main__":

    finders = [
        # UIST
        {
            "name": "uist",
            "config_name": "acm",
            "search_parameters": {
                'fillQuickSearch': 'false',
                'ContentItemType': 'research-article',
                'SpecifiedLevelConceptID': '119271',
                'expand': 'dl',
                'AfterMonth': '1',
                'AfterYear': '2000',
                'BeforeMonth': '12',
                'BeforeYear': '2019',
                'AllField': 'Title:((select* OR manipulat*) AND ("virtual" OR "VR")) OR Abstract:((select* OR manipulat*) AND ("virtual" OR "VR"))'
            }
        },
        # CHI
        {
            "name": "chi",
            "config_name": "acm",
            "search_parameters": {
                'fillQuickSearch': 'false',
                'ContentItemType': 'research-article',
                'SpecifiedLevelConceptID': '119596',
                'expand': 'dl',
                'AfterMonth': '1',
                'AfterYear': '2000',
                'BeforeMonth': '12',
                'BeforeYear': '2019',
                'AllField': 'Title:((select* OR manipulat*) AND ("virtual" OR "VR")) OR Abstract:((select* OR manipulat*) AND ("virtual" OR "VR"))'
            }
        },
        # IEEEVR
        {
            "name": "ieeevr",
            "config_name": "ieee",
            "search_parameters": {
                "action":"search",
                "matchBoolean":'True',
                "newsearch":'True',
                "queryText":"((((\"Document Title\": \"select*\" OR \"Document Title\": \"manipulat*\") AND (\"Document Title\": \"virtual\" OR \"Document Title\": \"VR\")) OR ((\"Abstract\": \"select*\" OR \"Abstract\": \"manipulat*\") AND (\"Abstract\": \"virtual\" OR \"Abstract\": \"VR\"))) AND (\"Publication Number\": 8787730 OR \"Publication Number\": 8423729 OR \"Publication Number\": 7889401 OR \"Publication Number\": 7499993 OR \"Publication Number\": 7167753 OR \"Publication Number\": 6786176 OR \"Publication Number\": 6542301 OR \"Publication Number\": 6179238 OR \"Publication Number\": 5753662 OR \"Publication Number\": 5440859 OR \"Publication Number\": 4806856 OR \"Publication Number\": 4472735 OR \"Publication Number\": 4160976 OR \"Publication Number\": 11055 OR \"Publication Number\": 9989 OR \"Publication Number\": 9163 OR \"Publication Number\": 8471 OR \"Publication Number\": 7826 OR \"Publication Number\": 7269 OR \"Publication Number\": 6781))",
                "highlight":'True',
                "returnFacets":["ALL"],
                "returnType":"SEARCH",
                "matchPubs":'True'
            },
            'headers': {
                'Cookie': "TS01b03060_26=014082121d70df1295452f0415c1d19d6df9a6f4e38bd41c2416ed80d5811061c6870f476e50edbc299092405b397624fa7a9e687bc99f8ff8a3910f51ad7f146893751e06; s_sq=%5B%5BB%5D%5D; WT_FPC=id=e72f05a8-a59d-4ec5-aec4-1152a199d9c3:lv=1595292510272:ss=1595292510272; JSESSIONID=GUl75h76VZMOs-zuTCaJlFC4zcJ3yP6wtx-cjO8IeePXFReL5bCx!-680779053; ERIGHTS=qdfpefSlqu3uiCGuTKfJucHgx2BppfxxYF3*xxqgiIyDwkBkIPSB6fG511wx3Dx3D-18x2dsWA2HgFqGnNTPTpUU0DGKQx3Dx3DdYHuM4AonsaMwzx2BLPW6f1Ax3Dx3D-seCuihlon4Yn6ravae9KzQx3Dx3D-x2BoJmAJK1Z3DbmTWzFvGVAAx3Dx3D; utag_main=v_id:01735d32e2490000e5080caf193f03072007c06a00fb8$_sn:7$_ss:0$_st:1595513350925$vapi_domain:ieee.org$_se:6$ses_id:1595511548855%3Bexp-session$_pn:1%3Bexp-session; AMCV_8E929CC25A1FB2B30A495C97%40AdobeOrg=1687686476%7CMCIDTS%7C18464%7CMCMID%7C20641728764065869141128774931607118228%7CMCAAMLH-1596116353%7C6%7CMCAAMB-1596116353%7CRKhpRz8krg2tLO6pguXWp5olkAcUniQYPHaMWWgdJ3xzPWQmdj0y%7CMCOPTOUT-1595518753s%7CNONE%7CMCAID%7CNONE%7CvVersion%7C3.0.0; xpluserinfo=eyJpc0luc3QiOiJ0cnVlIiwiaW5zdE5hbWUiOiJDb3BlbmhhZ2VuIFVuaXZlcnNpdHkiLCJwcm9kdWN0cyI6IklFTHxNQ1NZTlRINXxNQ1NZTlRIMXxNQ1NZTlRIM3xNQ1NZTlRINHxNQ1NZTlRIMnxNQ1NZTlRIN3xNQ1NZTlRIOHxNQ1NZTlRINnxNQ1NZTlRIOXxNQ1NZTlRIMTB8VkRFfE5PS0lBIEJFTEwgTEFCU3wifQ==; seqId=2644566; WLSESSION=237134476.20480.0000; TS01b03060=012f350623fd5c8dfef53c8016f92209f692fbb878553da77b0d7cb39209593f4e4b723514009901f6c5b52df817feb4a48b460b42d9df924fe4900f2a2d526564dca63f806c55f1e5df6976d59309bdc6da9da559289a09cdd40962dbf4e8de8db87317cf64aab18502ee0ab644b7f10d146a97046589963400ea55e921974f69ce15ca4f1c31e52480121d523b747f9a1b386f836d70ce861539d87205e46153e534c03bdbbad660826925cd8c3991f7bb8ecf77"
            }
        },
        # Virtual Reality (Journal)
        {
            "name": "vr",
            "config_name": "springer",
            "search_parameters": {
                'query': '((select* OR manipulat*) AND ("virtual" OR "VR"))',
                'facet-start-year': '2000',
                'date-facet-mode': 'between',
                'facet-end-year': '2019',
                'showAll[0]': 'false',
                'showAll[1]': 'true',
                'search-within': 'Journal',
                'facet-journal-id': '10055',
            }
        },
        # VRST
        {
            "name": "vrst",
            "config_name": "acm",
            "search_parameters": {
                'fillQuickSearch': 'false',
                'ContentItemType': 'research-article',
                'SpecifiedLevelConceptID': '119205',
                'expand': 'dl',
                'AfterMonth': '1',
                'AfterYear': '2000',
                'BeforeMonth': '12',
                'BeforeYear': '2019',
                'AllField': 'Title:((select* OR manipulat*) AND ("virtual" OR "VR")) OR Abstract:((select* OR manipulat*) AND ("virtual" OR "VR"))'
            }
        },
        # # Journal of Human-Computer Interaction
        # {
        #     "name": "hci",
        #     "config_name": "taylor_and_francis",
        #     "search_parameters": {
        #         'AllField': 'Title:((select* OR manipulat*) AND ("virtual" OR "VR")) OR Abstract:((select* OR manipulat*) AND ("virtual" OR "VR"))',
        #         'content': 'standard',
        #         'target': 'default',
        #         'queryID': '60/3256804055',
        #         'AfterYear': '2000',
        #         'BeforeYear': '2019',
        #         'SeriesKey': 'hihc20',
        #     },
        # },
        # # International Journal of Human-Computer Studies
        # {
        #     "name": "hcs",
        #     "config_name": "sciencedirect",
        #     "search_parameters": {
        #         'pub': 'International Journal of Human-Computer Studies',
        #         'cid': '272548',
        #         'date': '2000-2019',
        #         'tak': '(virtual OR VR) AND (select OR selecting OR selection OR selects OR manipulate OR manipulating OR manipulation)',
        #         'articleTypes': 'FLA',
        #     },
        # },
        # # TOCHI
        # {
        #     "name": "tochi",
        #     "config_name": "acm",
        #     "search_parameters": {
        #         'fillQuickSearch': 'false',
        #         'ContentItemType': 'research-article',
        #         'SeriesKey': 'tochi',
        #         'expand': 'dl',
        #         'AfterMonth': '1',
        #         'AfterYear': '2000',
        #         'BeforeMonth': '12',
        #         'BeforeYear': '2019',
        #         'AllField': 'Title:((select* OR manipulat*) AND ("virtual" OR "VR")) OR Abstract:((select* OR manipulat*) AND ("virtual" OR "VR"))'
        #     }
        # },
    ]

    tic = time.perf_counter()
    
    identifier_file = './identifiers.csvs'
    restrict = pd.read_csv(identifier_file, header=None)[0].to_list() if h.check_file_exists(identifier_file) else []

    fp = "./restricted.csv"
    fp2 = './pdf_pages.csv'
    # os.remove(fp)
    # os.remove(fp2)

    for finder in finders:
        find = Fetcher(restrict_identifiers_to=restrict, **finder)
        find.run()
        # find.export_results_to_csv(['title', 'authors', 'doi', 'identifier', 'pdf_url'], file_path=fp)
        # find.export_results_to_csv(['identifier'], file_path='./ids.csv')
        # find.download_pdfs()
        # find.export_results_to_csv(['pdf_num_pages'], file_path=fp2, defaults={'pdf_num_pages': 0})
    toc = time.perf_counter()
    h.console_down()
    print(f"Finished everything in {toc - tic:0.4f} seconds\n")