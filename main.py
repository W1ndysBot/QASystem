import logging
import os
import sys
import re
import sqlite3
import jieba
from Levenshtein import distance as levenshtein_distance  # 引入Levenshtein距离

# 添加系统路径
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


# 设置数据库路径
def get_db_path(group_id):
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data",
        "QASystem",
        f"{group_id}_qa_system.db",
    )


from app.api import *
from app.config import owner_id
from app.switch import load_switch, save_switch


# 初始化数据库
def init_db(group_id):
    db_path = get_db_path(group_id)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS QASystem (
            question TEXT NOT NULL UNIQUE,
            answer TEXT NOT NULL,
            keywords TEXT NOT NULL
        )
    """
    )
    conn.commit()
    conn.close()


# 检查是否是群主
def is_group_owner(role):
    return role == "owner"


# 检查是否是管理员
def is_group_admin(role):
    return role == "admin"


# 检查是否有权限（管理员、群主或root管理员）
def is_authorized(role, user_id):
    is_admin = is_group_admin(role)
    is_owner = is_group_owner(role)
    return (is_admin or is_owner) or (user_id in owner_id)


# 计算编辑距离
def calculate_similarity(a, b):
    max_len = max(len(a), len(b))
    if max_len == 0:
        return 1.0  # 两个空字符串相似度为1
    return 1 - levenshtein_distance(a, b) / max_len  # 归一化相似度


# 分词
def extract_keywords(text):
    keywords = jieba.lcut(text)  # 使用全模式分词
    return " ".join(sorted(keywords))  # 返回排序后的字符串


# 计算最高相似度,text1是用户输入,text2是数据库中的问题
def calculate_highest_similarity(text1, text2):
    keywords1 = extract_keywords(text1).split()
    keywords2 = extract_keywords(text2).split()

    # 计算编辑距离相似度
    return calculate_similarity(" ".join(keywords1), " ".join(keywords2))


# 添加或更新问答对
async def add_or_update_qa_pair(group_id, question, answer):
    try:
        keywords = extract_keywords(question)
        db_path = get_db_path(group_id)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO QASystem (question, answer, keywords) VALUES (?, ?, ?)",
            (question, answer, keywords),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.error(f"添加或更新问答对失败: {e}")
        return False


# 删除问答对
async def delete_qa_pair(group_id, question):
    try:
        db_path = get_db_path(group_id)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM QASystem WHERE question = ?", (question,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.error(f"删除问答对失败: {e}")
        return False


# 查看问答对列表
async def list_QASystem(group_id):
    try:
        db_path = get_db_path(group_id)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT question, answer FROM QASystem")
        data = cursor.fetchall()
        conn.close()
        return data
    except Exception as e:
        logging.error(f"查看问答对列表失败: {e}")
        return []


# 管理知识库命令处理
async def manage_knowledge_base(
    websocket, group_id, message_id, raw_message, user_id, role
):
    try:
        if is_authorized(role, user_id):
            # 处理开关命令
            if raw_message.startswith("qa-on"):
                if load_switch(group_id, "知识库"):
                    await send_group_msg(
                        websocket,
                        group_id,
                        f"[CQ:reply,id={message_id}] 知识库已经开启了，无需重复开启",
                    )
                else:
                    save_switch(group_id, "知识库", True)
                    await send_group_msg(
                        websocket,
                        group_id,
                        f"[CQ:reply,id={message_id}] 知识库已开启",
                    )
                return True  # 确保处理完命令后返回

            elif raw_message.startswith("qa-off"):
                if not load_switch(group_id, "知识库"):
                    await send_group_msg(
                        websocket,
                        group_id,
                        f"[CQ:reply,id={message_id}] 知识库已关闭，无需重复关闭",
                    )
                else:
                    save_switch(group_id, "知识库", False)
                    await send_group_msg(
                        websocket,
                        group_id,
                        f"[CQ:reply,id={message_id}] 知识库已关闭",
                    )
                return True  # 确保处理完命令后返回

            # 处理批量添加或更新问答对命令
            if raw_message.startswith("qa-add"):
                lines = raw_message.splitlines()
                success_count = 0
                for line in lines:
                    match = re.match(
                        r"qa-add(.+?) (.+)",
                        line.strip(),
                        re.DOTALL,
                    )
                    if match:
                        question = match.group(1).strip()
                        answer = match.group(2).strip()
                        if await add_or_update_qa_pair(group_id, question, answer):
                            success_count += 1

                content = (
                    f"[CQ:reply,id={message_id}]"
                    + f"批量添加或更新完成，成功处理了 {success_count} 条问答对。"
                )
                await send_group_msg(websocket, group_id, content)
                return True  # 确保处理完命令后返回

            # 识别删除问答对命令
            match = re.match(r"qa-rm(.+)", raw_message)
            if match:
                question = match.group(1)
                if await delete_qa_pair(group_id, question):
                    content = (
                        f"[CQ:reply,id={message_id}]"
                        + "删除成功\n"
                        + "问题："
                        + question
                    )
                    await send_group_msg(websocket, group_id, content)
                return True  # 确保处理完命令后返回

            # 识别查看问答对列表命令
            if raw_message.startswith("qa-list"):
                QASystem = await list_QASystem(group_id)
                messages = []
                await send_group_msg(
                    websocket,
                    group_id,
                    f"[CQ:at,qq={user_id}] 知识库问答对列表加载中...",
                )
                message_content = ""
                for index, (question, answer) in enumerate(QASystem):
                    message_content += f"问题：{question}\n答案：{answer}\n\n"
                    if (index + 1) % 5 == 0 or index == len(
                        QASystem
                    ) - 1:  # 每五条或者最后一条
                        messages.append(
                            {
                                "type": "node",
                                "data": {
                                    "name": "知识库问答对",
                                    "uin": "2769731875",
                                    "content": message_content,
                                },
                            }
                        )
                        message_content = ""  # 重置消息内容，为下一个节点准备
                await send_forward_msg(websocket, group_id, messages)
                return True  # 确保处理完命令后返回

            # 识别比较两个词语相似度命令
            if raw_message.startswith("qa-solo"):
                if await compare_similarity(
                    websocket, group_id, message_id, raw_message
                ):
                    return True  # 确保处理完命令后返回

    except Exception as e:
        logging.error(f"管理知识库失败: {e}")
        return False

    return False  # 如果不属于管理命令，则返回False，继续识别问题


# 识别问题返回答案
async def identify_question(websocket, group_id, message_id, raw_message):
    try:
        if load_switch(group_id, "知识库"):
            db_path = get_db_path(group_id)
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT question, answer, keywords FROM QASystem")
            data = cursor.fetchall()
            conn.close()

            raw_message_keywords = extract_keywords(raw_message).split()

            # 先计算总体相似度
            best_match = None
            highest_similarity = 0.0

            for question, answer, keywords in data:
                db_keywords = keywords.split()
                similarity = calculate_highest_similarity(
                    " ".join(raw_message_keywords), " ".join(db_keywords)
                )
                if similarity > highest_similarity:
                    highest_similarity = similarity
                    best_match = (question, answer, similarity)

            if best_match and highest_similarity > 0.75:  # 设置一个相似度阈值
                logging.info(f"识别到问题: {best_match[0]}")
                answer = (
                    best_match[1]
                    .replace("&#91;", "[")
                    .replace("&#93;", "]")
                    .replace("\\n", "\n")
                )
                content = f"[CQ:reply,id={message_id}]匹配到的问题：{best_match[0]}\n{answer}\n\n[+]匹配通道：总体相似度匹配\n[+]与数据库匹配相似度：{best_match[2]}\n[+]技术支持：easy-qfnu.top"
                await send_group_msg(websocket, group_id, content)
                return True  # 返回True表示识别到问题

            # 如果没有总体相似度匹配成功，再计算局部包含关系
            for question, answer, keywords in data:
                db_keywords = keywords.split()
                match_count = sum(
                    1 for keyword in db_keywords if keyword in raw_message_keywords
                )
                match_ratio = match_count / len(db_keywords)

                # 检查局部包含关系，设置匹配比例阈值
                if match_ratio >= 0.8:
                    logging.info(f"局部匹配到问题: {question}")
                    answer = (
                        answer.replace("&#91;", "[")
                        .replace("&#93;", "]")
                        .replace("\\n", "\n")
                    )
                    content = f"[CQ:reply,id={message_id}]匹配到的问题：{question}\n\n{answer}\n\n[+]匹配通道：局部包含关系匹配\n[+]与数据库匹配相似度：{match_ratio}\n[+]技术支持：easy-qfnu.top"
                    await send_group_msg(websocket, group_id, content)
                    return True

            return False
    except Exception as e:
        logging.error(f"识别知识库问题返回答案异常: {e}")
        return False


# 识别比较两个词语相似度命令
async def compare_similarity(websocket, group_id, message_id, raw_message):
    try:
        match = re.match(r"qa-solo(.+?) (.+)", raw_message)
        if match:
            word1 = match.group(1)
            word2 = match.group(2)
            # 提取关键词
            keywords1 = extract_keywords(word1)
            keywords2 = extract_keywords(word2)
            # 计算相似度
            similarity = calculate_similarity(keywords1, keywords2)
            content = (
                f"[CQ:reply,id={message_id}]"
                + f"词语 '{word1}' 和 '{word2}' 提取关键词后相似度为：{similarity:.9f}"
            )
            await send_group_msg(websocket, group_id, content)
            return True
        return False
    except Exception as e:
        logging.error(f"比较词语相似度失败: {e}")
        return False


# 问答系统菜单
async def QASystem(websocket, group_id, message_id):
    message = (
        f"[CQ:reply,id={message_id}]\n"
        + """
问答系统

qa-on 开启问答系统
qa-off 关闭问答系统
qa-add 添加问答
qa-rm 删除问答
"""
    )
    await send_group_msg(websocket, group_id, message)


# 知识库处理消息
async def handle_qasystem_message_group(websocket, msg):
    try:
        group_id = str(msg.get("group_id", ""))
        message_id = str(msg.get("message_id", ""))
        raw_message = str(msg.get("raw_message", ""))
        user_id = str(msg.get("user_id", ""))
        role = str(msg.get("sender", {}).get("role", ""))

        # 初始化数据库
        init_db(group_id)

        if raw_message == "qasystem":
            await QASystem(websocket, group_id, message_id)

        # 先尝试管理知识库
        management_handled = await manage_knowledge_base(
            websocket, group_id, message_id, raw_message, user_id, role
        )

        # 如果不是管理命令，再尝试识别问题
        if not management_handled:
            await identify_question(websocket, group_id, message_id, raw_message)

    except Exception as e:
        logging.error(f"知识库处理消息异常: {e}")
        return False
