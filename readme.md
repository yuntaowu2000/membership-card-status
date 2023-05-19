# UTCGA 微信会员卡

## Setup：

### Function App
- [图文](https://learn.microsoft.com/en-us/azure/azure-functions/create-first-function-vs-code-python?pivots=python-mode-configuration)

简略版：
- Azure portal开启Function App service
- VS Code安装Azure Functions插件
- 左侧panel进入Azure面板，resources中选择function App，点+号，选择create function app，根据指示建立app
- 之后在workspace中可以找到刚建立的function app，选择后点击create function即可建立模板。
  - 选择http trigger即为http request触发
  - 主要代码在创建的文件夹的__init__.py
  - 生成的`local.settings.json`中加入以下"Host"的CORS policy，允许任意ip进入：
  ```
  "Values": {},
  "Host": {
    "CORS": "*"
  }
  ```
- Run & Debug可以进行local测试，可以debug的同时运行另一个python文件发送request进行测试。
- 测试完成后，在workspace中选择deploy即可直接部署到azure上开始运行。
  - azure上的api节点为：`https://{function-app-name}.azurewebsites.net/api/{function-name}`，所有的request都需要进入这个节点
  - azure上同样在Function App-API-CORS中设置Allowed Origin: *

### Cosmos DB
- Azure Portal开启Azure Cosmos DB service
  - 选择MongoDB
  - location: 和function app的location一致
  - capacity mode: provisioned throughput
  - apply free tier discount，基本可以一直免费，[介绍](https://learn.microsoft.com/en-us/azure/cosmos-db/free-tier)
  - version 4.2
  - backup policy: periodic, keep 2，免费而且没啥用，因为我们一定会下载一份
- DB service建立后
  - Overview中选择建立New Collection，建立database和collection，记录下database name和collection id
  - 记录settings-connection strings中的PRIMARY CONNECTION STRING，用于代码中的DB连接
  - Data Explorer中可看到所有的data
    - 选择一个collection，settings中可以设置index，我们可以将用户的open_id也设置为一个single field的index

### 本地/Githubupload配置

App本地测试运行以及通过vscode上传至Azure时默认两个文件存在：
- `.jsonfiles/email.json`
  - JSON dictionary 记录以下field：
  - `"server"`：email的SMTP服务器
  - `"user"`：发送邮件的邮箱，需要能通过server的验证
  - `"key"`：邮箱对应的密码，建议用没有2FA或OAUTH的SMTP提供商如purelymail
  - `"to"`：一个收件人的list（有哪些人需要接收到这里所有的相关信息）
- `.jsonfiles/database.json`
  - JSON dictionary 记录以下field：
  - `"cosmos_conn_str"`：Azure cosmos的链接，即为settings-connection strings中的PRIMARY CONNECTION STRING
  - `"db_name"`：需要使用的mongodb的database名字
  - `"collection_name"`：database下需要使用的collection的名字

使用Github CI上传至Azure时默认三个Action secret存在：
- `EMAIL_DATA`：`.jsonfiles/email.json`的raw text形式，one line，所有`"`号需要用`\"` escape。
- `DB_DATA`：`.jsonfiles/database.json`的raw text形式，one line，所有`"`号需要用`\"` escape。
- `AZURE_FUNCTIONAPP_PUBLISH_PROFILE`：Function App的Overview中可以点击`Get publish profile`获取`membership-card-status.PublishSettings`文件，将文件内容直接复制进secret即可。