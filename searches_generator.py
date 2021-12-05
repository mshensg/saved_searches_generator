#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Dec  5 17:44:41 2021

@author: mshensg

script not completed yet

"""

import requests, json, re, datetime
import csv,random, urllib
random.seed()
requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)

def log_info(action,entry):
    message = json.dumps({
        "_timestamp": str(datetime.datetime.now()),
        "action": action,
        "reference": entry
    })
    print(message)
    #write to log file, later define a lot file name

configuration={
    "name": "search",
    "template_report": "project_template_report",
    "template_fields": ["actions","schedule_priority","is_scheduled", "schedule_window","dispatch.earliest_time","dispatch.latest_time","cron_schedule","disabled","description"],
    "sharing": "app",
    "application":"reporting_app",
    "overwrite_existing": True,
    "skip_fields_overwrite":["cron_schedule", "search"],
    "update_fields":{
        "search": '''|tstats count by index
        | eval value=count."%project%"''',
        "action.email.to": "%to%",
        "action.email.cc": "%cc%",
        "action.email.subject": "test email reports - $name$",
        "action.email.description": "this is a sample $name$",
        "name": "%project% sample report",
        "actions": "email",
        "cron_schedule":"rand(0,15) rand(1,6) * * 1"
    },
    "search_template":"search.spl",
    "template_fields_csv":"projects.csv"
}

#import yaml
#a=yaml.safe_load(c)

yaml_configuration="""
application: reporting_app
name: search
overwrite_existing: true
sharing: app
skip_fields_overwrite: #the fields will be ignored for writing the existing report
- cron_schedule
- search
template_fields: #the fields will be loaded from the template
- actions
- search
- schedule_priority
- is_scheduled
- schedule_window
- dispatch.earliest_time
- dispatch.latest_time
- cron_schedule
- disabled
- description
template_report: project_template_report
template_fields_csv: projects.csv
update_fields:
  action.email.cc: '%cc%'
  action.email.description: this is a sample $name$
  action.email.subject: test email reports - $name$
  action.email.to: '%to%'
  actions: email
  cron_schedule: rand(0,15) rand(1,6) * * 1 #rand to randomize the number in a range
  name: '%project% sample report'
  search: | #all lines need indents
    |tstats count by index
    |eval value=count."%project%"
"""

if "search_template" in configuration and type(configuration["search_template"] is str):
    with open(configuration["search_template"],"r") as f:
        c=f.readlines()
    search=''.join(c)
    configuration["update_fields"]["search"]=search

log_info("configuration loaded", configuration)

sharing="app" \
    if ("sharing" not in configuration or configuration["sharing"] not in ["app", "user", "global"]) else configuration["sharing"]
template_fields=["actions","schedule_priority","schedule_window","dispatch.earliest_time","dispatch.latest_time","cron_schedule","disabled","description"] \
    if ("template_fields" not in configuration or type(configuration["template_fields"]) is not list) else configuration["template_fields"]
overwrite_existing=False \
    if ("overwrite_existing" not in configuration or type(configuration["overwrite_existing"]) is not bool) else configuration["overwrite_existing"]
skip_fields_overwrite=[] \
    if ("skip_fields_overwrite" not in configuration or type(configuration["skip_fields_overwrite"]) is not list) else configuration["skip_fields_overwrite"]

server="<IPMASKS>"
port=8089
user="~~~~~~"
password="~~~~~~"

if "template_report" in configuration and type(configuration["template_report"]) is str:
    application= "-" if ("application" not in configuration or type(configuration["application"]) is not str) else configuration["application"]
    url = "https://{}:{}/servicesNS/-/{}/saved/searches/{}".format(server,port,application,urllib.parse.quote(configuration["template_report"]))
    params = {
        "output_mode":"json",
        "listDefaultActionArgs":True,
        "f":template_fields,
        "count":1
    }
    headers = {}
    response = requests.get(url,auth=(user,password),headers=headers,params=params, verify=False)
    if response.status_code == 200:
        rest_template = [i for i in response.json()["entry"] if i["name"]==configuration["template_report"]]
        if len(rest_template)>0:
            template_report_configuration = rest_template[0]["content"]
            template_report={**template_report_configuration,**configuration["update_fields"]}
            # assume the reports will be created in the same application as the template
            found_in_application = rest_template[0]["acl"]["app"]
            configuration["application"]=found_in_application
            
if not template_report:
    print("No default template specified or specified template does not exist")
    template_report=configuration["update_fields"]
    log_info("template generated", template_report)
    
    
records=[]
with open(configuration['template_fields_csv'], newline='') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        records.append(row)
        
generated_reports=[]
crongen = re.compile("([a-z]+)\((\d+)\,(\d+)\)")

for record in records:
    report_configuration=template_report.copy()
    for i in template_report.keys():
        if type(report_configuration[i]) is str and "%" in report_configuration[i]:
            for j in record.keys():
                report_configuration[i] = report_configuration[i].replace("%"+j+"%", record[j])
        if i=="cron_schedule":
            parts=template_report[i].split(" ")
            cron=""
            for k in parts:
                results=crongen.match(k)
                if results and results.groups()[0] == "rand" and results.groups()[1].isnumeric() and results.groups()[2].isnumeric():
                    number=random.randrange(int(results.groups()[1]),int(results.groups()[2])+1)
                    k=number
                cron+=str(k)+" "
            report_configuration[i]=cron.strip()
    generated_reports.append(report_configuration)
    
if sharing in ["app","global"]:
    user_context = "nobody"
else:
    user_context = user

creation_url="https://{}:{}/servicesNS/{}/{}/saved/searches/".format(server,port,user_context,configuration["application"])

post_params={
    "output_mode":"json",
}

results=[]

for report_request in generated_reports:
    verify_url = "https://{}:{}/servicesNS/-/{}/saved/searches/{}".format(server,port,configuration["application"],urllib.parse.quote(report_request["name"]))
    params = {
        "output_mode":"json",
        "f":["is_scheduled"],
        "count":1
    }
    headers = {}
    verify = requests.get(verify_url,auth=(user,password),headers=headers,params=params, verify=False)
    if verify.status_code == 200:
        print("Existing report found in the same name")
        if overwrite_existing:
            overwrite_url = verify.json()["entry"][0]["id"]
            update_request = {i:report_request[i] for i in report_request.keys() if i!="name" and i not in skip_fields_overwrite}
            response = requests.post(overwrite_url,auth=(user,password),params=post_params, data=update_request, verify=False)
            log_info("replace existing report",{
                "report":report_request["name"],
                "type":"overwrite existing",
                "existing_id":overwrite_url,
                "skipped_fields": skip_fields_overwrite,
                "updated_values": update_request,
                "response_code": response.status_code,
                "response_text": response.text if response.status_code not in [200,201] else "Succeeded"
            })
        else:
            log_info("skip replace existing report", {
                "report":report_request["name"],
                "type":"skip existing"
            })
    else:
        response = requests.post(creation_url,auth=(user,password),params=post_params, data=report_request, verify=False)
        log_info("new report created", {
            "report":report_request["name"],
            "type":"create new",
            "existing_id":creation_url,
            "updated_values": report_request,
            "response_code": response.status_code,
            "response_text": response.text if response.status_code not in [200,201] else "Succeeded"
        })
