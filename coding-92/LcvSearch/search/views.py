import json
from django.shortcuts import render
from django.views.generic.base import View
from search.models import ArticleType
from django.http import HttpResponse
from elasticsearch import Elasticsearch
from datetime import datetime
import redis

client = Elasticsearch(hosts=["127.0.0.1"])
redis_cli = redis.StrictRedis(decode_responses=True)


class IndexView(View):
    #首页
    def get(self, request):
        topn_search = redis_cli.zrevrangebyscore("search_keywords_set", "+inf", "-inf", start=0, num=5)
        return render(request, "index.html", {"topn_search":topn_search})

# Create your views here.
class SearchSuggest(View):
    def get(self, request):
        key_words = request.GET.get('s','')
        re_datas = []
        if key_words:
            s = ArticleType.search()
            s = s.suggest('my_suggest', key_words, completion={
                "field":"suggest", "fuzzy":{
                    "fuzziness":2
                },
                "size": 10
            })
            suggestions = s.execute_suggest()
            for match in suggestions.my_suggest[0].options:
                source = match._source
                re_datas.append(source["title"])
        return HttpResponse(json.dumps(re_datas), content_type="application/json")


class SearchView(View):
    def get(self, request):
        key_words = request.GET.get("q","")
        s_type = request.GET.get("s_type", "article")
        index_name = "jobbole"
        source = "cnblogs"
        if s_type == "job":
            index_name = "lagou"
            source = "拉勾网"
        if s_type == "question":
            index_name = "zhihu"
            source = "知乎"

        redis_cli.zincrby("search_keywords_set", 1, key_words)

        topn_search = redis_cli.zrevrangebyscore("search_keywords_set", "+inf", "-inf", start=0, num=5)
        page = request.GET.get("p", "1")
        try:
            page = int(page)
        except:
            page = 1

        jobbole_count = redis_cli.get("jobbole_count")
        start_time = datetime.now()
        response = client.search(
            index= index_name,
            body={
                "query":{
                    "multi_match":{
                        "query":key_words,
                        "fields":["tags", "title", "content", "job_desc"]
                    }
                },
                "from":(page-1)*10,
                "size":10,
                "highlight": {
                    "pre_tags": ['<span class="keyWord">'],
                    "post_tags": ['</span>'],
                    "fields": {
                        "title": {},
                        "content": {},
                    }
                }
            }
        )
        print(response)

        end_time = datetime.now()
        last_seconds = (end_time-start_time).total_seconds()
        total_nums = response["hits"]["total"]
        if (page%10) > 0:
            page_nums = int(total_nums/10) +1
        else:
            page_nums = int(total_nums/10)
        hit_list = []
        for hit in response["hits"]["hits"]:
            from collections import defaultdict
            hit_dict = defaultdict(str)
            if "highlight" not in hit:
                hit["highlight"] = {}
            if "title" in hit["highlight"]:
                hit_dict["title"] = "".join(hit["highlight"]["title"])
            else:
                hit_dict["title"] = hit["_source"]["title"]

            if index_name == "lagou":
                if "job_desc" in hit["highlight"]:
                    hit_dict["content"] = "".join(hit["highlight"]["job_desc"])[:500]
                else:
                    hit_dict["content"] = hit["_source"]["job_desc"][:500]
            elif index_name == "jobbole":
                if "content" in hit["highlight"]:
                    hit_dict["content"] = "".join(hit["highlight"]["content"])[:500]
                else:
                    hit_dict["content"] = hit["_source"]["content"][:500]

            if "create_date" in hit_dict:
                hit_dict["create_date"] = hit["_source"]["create_date"]
            if "publish_time" in hit["_source"]:
                hit_dict["create_date"] = hit["_source"]["publish_time"]
            hit_dict["url"] = hit["_source"]["url"]
            hit_dict["score"] = hit["_score"]

            hit_list.append(hit_dict)

        return render(request, "result.html", {"page":page,
                                               "all_hits":hit_list,
                                               "key_words":key_words,
                                               "total_nums":total_nums,
                                               "page_nums":page_nums,
                                               "source":source,
                                               "s_type":s_type,
                                               "index_name":index_name,
                                               "last_seconds":last_seconds,
                                               "jobbole_count":jobbole_count,
                                               "topn_search":topn_search})
