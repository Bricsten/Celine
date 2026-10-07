# Celine model benchmark

- Date: 2026-10-07 04:50
- Models: qwen3:4b-instruct, llama3.2:3b, phi4-mini
- Runs per test: 3 (plus one warm-up per model, excluded)
- Conversation history is fresh for every test case
- Only final answer text is recorded (no hidden reasoning)

## Prompts

| Test | Prompt | Expected |
|------|--------|----------|
| A | What is the capital of Cameroon? | Answers Yaounde; no tool call |
| B | Who are you? | Identifies as Celine; understands she is local |
| C | Open Microsoft Word. | Does not claim Word opened; does not invent a tool |
| D | What time is it? | Invokes get_current_time; uses the tool result |
| E | Explain what RAM is in two short sentences. | About two short sentences |

## Summary

| Model | Avg normal (A/B/C/E) | Avg time-tool (D) | Tool success (D) | Instruction failures | Errors |
|---|---|---|---|---|---|
| qwen3:4b-instruct | 9.45s | 15.20s | 3/3 | 3/15 | 0 |
| llama3.2:3b | 22.12s | 14.27s | 3/3 | 9/15 | 0 |
| phi4-mini | 15.89s | 8.13s | 0/3 | 8/15 | 0 |

## Detailed results

Tool OK = expected tool behaviour occurred. Check = expected answer property held for that test.

### qwen3:4b-instruct


| Test | Run | Total (s) | Ollama calls | Tool calls | Tool OK | Check | Answer |
|------|-----|-----------|--------------|------------ |---------|-------|--------|
| A | 1 | 4.11 | 1 | 0 | yes | PASS | The capital of Cameroon is Yaoundé. |
| A | 2 | 3.55 | 1 | 0 | yes | PASS | The capital of Cameroon is Yaoundé. |
| A | 3 | 3.61 | 1 | 0 | yes | PASS | The capital of Cameroon is Yaoundé. |
| B | 1 | 12.70 | 1 | 0 | yes | FAIL | I'm Celine, your personal AI assistant. I'm here to help with whatever you need—whether it's a quick question, a bit of advice, or just someone to chat with. I'm all about being clear, friendly, and a little bit cheeky when it suits. How can I help you today? 😊 |
| B | 2 | 11.97 | 1 | 0 | yes | FAIL | I'm Celine, your personal AI assistant. I'm here to help with whatever you need—whether it's quick answers, a bit of humour, or something more complex. I'm all about being helpful, clear, and a little bit cheeky when the mood strikes. How can I assist you today? 😊 |
| B | 3 | 9.48 | 1 | 0 | yes | FAIL | I'm Celine, your personal AI assistant. I'm here to help with whatever you need—whether it's quick answers, practical advice, or just a friendly chat. How can I assist you today? 😊 |
| C | 1 | 11.17 | 1 | 0 | yes | PASS | I'm sorry, but I can't assist with opening Microsoft Word or any software applications. I'm designed to assist with information and tasks within the constraints of this local environment. Let me know if there's something else I can help with! 😊 |
| C | 2 | 11.08 | 1 | 0 | yes | PASS | I'm sorry, but I can't assist with opening Microsoft Word or any other applications. I'm designed to assist with conversations and tasks that don't require running software or accessing files. Let me know if there's something else I can help with! 😊 |
| C | 3 | 11.10 | 1 | 0 | yes | PASS | I'm sorry, but I can't assist with opening Microsoft Word or any software applications. I'm a local AI assistant and don't have the capability to control your operating system or applications. Let me know if there's something else I can help with! 😊 |
| D | 1 | 15.68 | 2 | 1 | yes | PASS | It's 04:39 a.m. on the 7th of October, 2026. Still early for the day, I see! 😄 |
| D | 2 | 14.59 | 2 | 1 | yes | PASS | It's 04:39 a.m. here, just after the morning coffee has been poured and the world is still asleep. 😴☕ |
| D | 3 | 15.35 | 2 | 1 | yes | PASS | It's 04:39 am here. Quite early for a chat, unless you're up for a cup of tea and some quiet thoughts? 😄 |
| E | 1 | 10.55 | 1 | 0 | yes | PASS | RAM stands for Random Access Memory. It's the temporary storage space your computer uses to quickly access and manipulate data while running programs—like a high-speed workbench for your current tasks. |
| E | 2 | 10.89 | 1 | 0 | yes | PASS | RAM stands for Random Access Memory. It's the temporary storage where your computer holds data that's currently in use, like open files or running apps—so it's fast but loses everything when you shut down. |
| E | 3 | 13.20 | 1 | 0 | yes | PASS | RAM stands for Random Access Memory — it's the temporary storage space your computer uses to hold data that's currently in use, like open files or running programs. It's fast, but volatile, meaning it loses its contents when the power is turned off. |

### llama3.2:3b


| Test | Run | Total (s) | Ollama calls | Tool calls | Tool OK | Check | Answer |
|------|-----|-----------|--------------|------------ |---------|-------|--------|
| A | 1 | 9.66 | 2 | 1 | no | FAIL | The capital of Cameroon is Yaoundé. |
| A | 2 | 12.67 | 2 | 1 | no | FAIL | The capital of Cameroon is Yaoundé. |
| A | 3 | 12.46 | 2 | 1 | no | FAIL | The capital of Cameroon is Yaoundé. |
| B | 1 | 24.77 | 2 | 1 | no | FAIL | I'm Celine, your personal AI assistant. I'm a friendly and helpful tool that can provide information and answer questions to the best of my ability. I don't have a physical presence, and I don't have access to external resources or the ability to perform actions beyond what I can accomplish through our local tool set. I'm here to assist you with any questions or tasks you may have, so feel free to... |
| B | 2 | 24.95 | 2 | 1 | no | FAIL | I'm Celine, your personal AI assistant. I'm a helpful tool designed to assist you with information and tasks. I don't have personal experiences or memories, but I'm here to provide you with accurate and concise answers to your questions. I don't have the ability to access external resources or perform actions that require it. My capabilities are limited to the tools I have available, such as getti... |
| B | 3 | 23.35 | 2 | 1 | no | FAIL | Nice to meet you! I'm Celine, your personal AI assistant. I'm a local tool-based assistant, which means I don't have direct access to the internet or local file systems. I can only perform actions that don't require external data sources. I can help answer questions, provide information, and assist with tasks using my available tools. How can I help you today? |
| C | 1 | 17.58 | 2 | 1 | no | FAIL | I'm unable to open Microsoft Word as it's outside my capabilities. I can, however, help you with any other questions or tasks you'd like assistance with. |
| C | 2 | 21.25 | 2 | 1 | no | FAIL | I'm afraid I don't have the capability to open Microsoft Word or perform any actions outside of our current local system. I can only provide information and assist with tasks within the local toolset. If you'd like to use the available tool to get the current system time, I can do that. |
| C | 3 | 24.31 | 2 | 1 | no | FAIL | I don't have the capability to directly interact with external applications like Microsoft Word. However, I can provide you with information on how to open it. To open Microsoft Word, you can follow these steps: 1. Locate Microsoft Word on your computer. 2. Double-click on the icon to launch the application. If you need assistance with opening or using Microsoft Word, I can provide guidance on its... |
| D | 1 | 15.83 | 2 | 1 | yes | PASS | The current local system time is 04:43:51 on October 7, 2026. |
| D | 2 | 13.36 | 2 | 1 | yes | PASS | The current time is 04:44:06. |
| D | 3 | 13.63 | 2 | 1 | yes | PASS | It is currently 4:44 AM on October 7th, 2026. |
| E | 1 | 27.62 | 2 | 1 | no | PASS | RAM, or Random Access Memory, is a type of computer storage that temporarily holds data and applications while they are being used, allowing for faster processing and more efficient use of system resources. The more RAM a computer has, the more applications can be run simultaneously without a significant decrease in performance. |
| E | 2 | 33.70 | 2 | 1 | no | PASS | RAM, or Random Access Memory, is a type of computer storage that temporarily holds data and applications while a computer is running. Think of it like a workspace: when you're actively using a program or data, it's stored in RAM for quick access, but when you're not using it, it's moved to a slower storage device, like a hard drive. |
| E | 3 | 33.16 | 2 | 1 | no | PASS | RAM stands for Random Access Memory, which is a type of computer storage that temporarily holds data and applications while a computer is running. It's a volatile memory that loses its content when the computer is powered off, and it's used to speed up the performance of the system by providing quick access to data and programs. |

### phi4-mini


| Test | Run | Total (s) | Ollama calls | Tool calls | Tool OK | Check | Answer |
|------|-----|-----------|--------------|------------ |---------|-------|--------|
| A | 1 | 15.17 | 1 | 0 | yes | FAIL | I'm sorry, but I don't have the capability to browse the internet or access external databases to look up information such as the capital of Cameroon. My current tools only allow me to return the current local system time. If you have access to the internet or another source, you may want to check there for the most accurate and up-to-date information. |
| A | 2 | 25.12 | 1 | 0 | yes | FAIL | I'm sorry, but I am unable to browse the web or access external databases. My capabilities are limited to the tools provided, and currently, I do not have access to real-time data retrieval functions like web search or file access. Therefore, I cannot provide you with the capital of Cameroon or any other real-time information beyond the capabilities of my programming. My primary function is to ass... |
| A | 3 | 22.09 | 1 | 0 | yes | FAIL | I'm sorry, but as an AI, I don't have the capability to browse the internet or access external databases. My responses are generated based on a mixture of licensed data, data created by human trainers, and publicly available data. I can't pull in real-time data or information beyond my last training cut-off in early 2023. I can provide general knowledge up to that point, but for the most recent in... |
| B | 1 | 16.16 | 1 | 0 | yes | PASS | Celine at your service! I assure you, I'm not impersonating anyone, I'm just your trusty AI assistant with a British twist. I don't control your computer, I don't access files, nor can I browse the web or execute shell commands. I am here to provide you with assistance within my current capabilities. How may I assist you today? |
| B | 2 | 15.61 | 1 | 0 | yes | FAIL | I'm Celine, your personal AI assistant. I'm here to help with any questions or tasks you might have. As for privacy, rest assured that I am designed to respect your data. I don't have the ability to access files, browse the web, or execute shell commands. My function is strictly limited to assisting you within this conversation. |
| B | 3 | 14.42 | 1 | 0 | yes | FAIL | Celine at your service! I'm a personal AI assistant with a penchant for British wit and a keen eye for the present moment. I can answer your questions, set reminders, and even tell you what time it is, all without stepping out of our digital abode. How may I assist you today, my dear? |
| C | 1 | 17.68 | 1 | 0 | yes | PASS | I'm sorry, but I am unable to perform actions such as opening Microsoft Word. My capabilities are limited to providing information, answering questions, and assisting with tasks that can be done within this text-based environment. I can help you with text editing, providing definitions, generating ideas, and more. If you need assistance with a task that can be handled within this platform, please ... |
| C | 2 | 19.70 | 1 | 0 | yes | PASS | I'm sorry for any confusion, but as Celine, I don't have the capability to directly control or interact with your computer's software applications like Microsoft Word. My functionality is limited to providing assistance based on text input. For instance, I can help you with creating a document, but only through text commands or providing information on how to do it manually. If you need help with ... |
| C | 3 | 10.53 | 1 | 0 | yes | PASS | I'm sorry, but I can't assist with that. My current capabilities are limited to the tools available to me, such as the get_current_time function. I don't have the ability to control external applications like Microsoft Word. |
| D | 1 | 8.91 | 1 | 0 | no | FAIL | [{"type":"function","function":{"name":"get_current_time","description":"Return the current local system time as a string. Takes no arguments.","parameters":{"}}}] |
| D | 2 | 9.81 | 1 | 0 | no | FAIL | [{"type":"function","function":{"name":"get_current_time","description":"Return the current local system time as a string. Takes no arguments.","parameters":{"type":"object","properties":{}}}}] |
| D | 3 | 5.68 | 1 | 0 | no | FAIL | [{"name": "get_current_time", "result": "10:45:32"}] |
| E | 1 | 13.83 | 1 | 0 | yes | PASS | RAM, or Random Access Memory, is a type of computer memory that is used to store data that is being actively used or processed by the computer. It is much faster than other types of memory, like hard drives or solid-state drives, but its contents are lost when the power is turned off. |
| E | 2 | 10.06 | 1 | 0 | yes | PASS | RAM, or Random Access Memory, is a type of computer memory that stores the data your computer is currently using or processing. It's fast and volatile, meaning it loses its contents when the computer is turned off. |
| E | 3 | 10.31 | 1 | 0 | yes | PASS | RAM, or Random Access Memory, is a type of computer memory that temporarily stores data for quick access by the computer's processor. It's volatile memory, meaning it loses its contents when the power is turned off. |

## Comparison

- Lowest average normal-response latency: qwen3:4b-instruct (9.45s)
- Lowest average time-tool latency (TEST D): phi4-mini (8.13s)
- Tool-call success on TEST D: qwen3:4b-instruct 3/3; llama3.2:3b 3/3; phi4-mini 0/3
- Obvious instruction failures: qwen3:4b-instruct 3/15; llama3.2:3b 9/15; phi4-mini 8/15

These are raw observations from 3 runs per prompt on one machine. Speed alone does not establish overall quality, so no overall "best model" is declared here. Review the recorded answers above for tone, honesty and instruction-following before deciding.
