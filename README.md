# QASystem

基于 NLP 和编辑距离算法的知识库问答系统

## 命令

qa-on 开启问答系统

qa-off 关闭问答系统

qa-add 添加问答

qa-rm 删除问答

qa-list 查看知识库问答对列表

qa-solo 对比两个句子的相似度

## 更新日志

2024 年 8 月 30 日，增加优先局部匹配，当局部分词匹配相似度超过 0.5 时，视为匹配成功，若无匹配结果，则进行下一步的总体相似度匹配，可以解决消息中包含过多数据库中没有的关键词时，无法匹配到问题的问题

2024 年 8 月 30 日，合并 add 和 update 命令，当添加问答对时，如果问题已存在，则更新问答对，在回答中，增加匹配到的问题，防止有时候引起歧义

2024 年 8 月 27 日，引入 jieba 中文分词和莱文斯坦距离，优化关键词识别逻辑，当收到消息时，连接数据库并查询所有的问题、答案和关键词 (SELECT question, answer, keywords FROM QASystem)。使用 jieba 库对用户发送的消息进行分词并提取关键词 (extract_keywords(raw_message))。遍历数据库中的所有问题，计算用户消息的关键词与数据库中每个问题的关键词的相似度 (calculate_similarity(raw_message_keywords, keywords))。记录相似度最高的问题和答案。如果相似度超过设定的阈值，则认为找到了匹配的问题。

2024 年 8 月 23 日，优化关键词触发之后的提示语

2024 年 8 月 22 日，增加关键词触发频率限制，每个关键词每 5 分钟最多触发一次

2024 年 8 月 18 日，增加关键词触发频率限制，每个关键词每 2 分钟最多触发一次

2024 年 8 月 15 日，优化关键词触发逻辑，当收到消息时，优先检查是否有相关问题，当有相关问题时，直接返回答案，如果没有相关问题，则返回关键词相关问题列表，避免了当收到的消息和存储的问题完全匹配时，先返回关键词相关问题列表，再返回答案，导致一个问题问两次的麻烦。

2024 年 8 月 14 日，增加对特殊字符的处理，实现可通过存入 cq 码的方式来实现存入图片、语音、视频等富文本信息

2024 年 8 月 12 日，重构代码，精简命令
