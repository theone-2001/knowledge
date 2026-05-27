#!/usr/bin/env python3
"""Telegram 연결 및 수신 — secretary_telegram_v4.

Secretary 에이전트의 텔레그램 연결 및 수신 도구.
토큰·chat_id를 기반으로 메시지를 전송하고,
사용자의 명령을 수신(Polling)하여 파일에 기록하며,
에이전트의 답변을 감지하여 텔레그램으로 회신합니다.
"""
import os, json, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "telegram_setup.json")
OFFSET_FILE = os.path.join(HERE, "telegram_offset.json")
HISTORY_FILE = os.path.join(HERE, "..", "telegram_history.jsonl")

def load_config():
    if not os.path.exists(CONFIG):
        print("❌ telegram_setup.json이 없어요. 먼저 설정을 완료해주세요.")
        sys.exit(1)
    try:
        with open(CONFIG, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ 설정 파일 파싱 실패: {e}")
        sys.exit(1)

def load_offset():
    if os.path.exists(OFFSET_FILE):
        try:
            with open(OFFSET_FILE, "r") as f:
                data = json.load(f)
                return data.get("offset")
        except:
            pass
    return None

def save_offset(offset):
    with open(OFFSET_FILE, "w") as f:
        json.dump({"offset": offset}, f)

def get_last_agent_ts():
    """기존 대화 기록에서 마지막 에이전트 답변의 타임스탬프를 가져옵니다."""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
                for line in reversed(lines):
                    data = json.loads(line.strip())
                    if data.get("role") == "assistant":
                        return data.get("ts")
        except:
            pass
    return int(time.time() * 1000) # 없으면 현재 시간

def main():
    cfg = load_config()
    token = (cfg.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat  = (cfg.get("TELEGRAM_CHAT_ID") or "").strip()
    
    if not token or not chat:
        print("❌ 토큰 또는 채팅 ID가 비어있어요.")
        sys.exit(1)
        
    try:
        import requests
    except ImportError:
        print("❌ pip install requests")
        sys.exit(1)
        
    # 1. 연결 테스트 (기존 기능 유지)
    body = f"✅ 비서(Secretary) 텔레그램 연결 정상 — {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n이제부터 이 창을 켜두시면 대표님의 메시지를 수신하고, 에이전트의 답변을 전달합니다."
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": body, "parse_mode": "Markdown"},
            timeout=15,
        )
        r.raise_for_status()
        print(f"✅ 테스트 전송 OK — 텔레그램에서 확인하세요.")
    except Exception as e:
        print(f"❌ 전송 실패: {e}")
        sys.exit(1)
        
    # 2. 메시지 수신 및 답변 감지 (Polling & Monitoring)
    print("\n📥 텔레그램 메시지 수신 및 에이전트 응답 감지를 시작합니다...")
    print("대표님께서 봇에게 메시지를 보내시면 여기에 표시되고 대화창에 기록됩니다.")
    print("에이전트(영숙 등)가 답변을 작성하면 텔레그램으로 자동 전송됩니다. (종료: Ctrl+C)")
    
    offset = load_offset()
    last_agent_ts = get_last_agent_ts()
    
    try:
        while True:
            # 2.1 텔레그램 메시지 수신 (User -> Agent)
            try:
                url = f"https://api.telegram.org/bot{token}/getUpdates"
                params = {"timeout": 10} # 타임아웃을 조금 줄여서 파일 감지도 원활하게
                if offset:
                    params["offset"] = offset
                    
                resp = requests.get(url, params=params, timeout=15)
                
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("ok") and data.get("result"):
                        for update in data["result"]:
                            update_id = update["update_id"]
                            offset = update_id + 1
                            save_offset(offset)
                            
                            if "message" in update:
                                msg = update["message"]
                                sender_chat_id = str(msg["chat"]["id"])
                                text = msg.get("text", "")
                                
                                # 지정된 사용자의 메시지만 처리 (보안)
                                if sender_chat_id == chat:
                                    print(f"[{time.strftime('%H:%M:%S')}] 대표님: {text}")
                                    
                                    # Connect AI 대화창에 표시되도록 파일에 기록
                                    try:
                                        with open(HISTORY_FILE, "a", encoding="utf-8") as hf:
                                            history_data = {
                                                "role": "user",
                                                "text": text,
                                                "ts": int(time.time() * 1000)
                                            }
                                            hf.write(json.dumps(history_data, ensure_ascii=False) + "\n")
                                        print("📝 Connect AI 대화창에 메시지가 기록되었습니다.")
                                    except Exception as e:
                                        print(f"⚠️ 대화창 기록 실패: {e}")
                                    
                                else:
                                    print(f"[주의] 알 수 없는 사용자({sender_chat_id})의 접근 차단")
                                    
            except requests.exceptions.ConnectionError:
                print("⚠️ 네트워크 연결 오류... 5초 후 재시도합니다.")
                time.sleep(5)
            except Exception as e:
                print(f"⚠️ 오류 발생: {e}")
                
            # 2.2 에이전트 답변 감지 및 전송 (Agent -> User)
            try:
                if os.path.exists(HISTORY_FILE):
                    with open(HISTORY_FILE, "r", encoding="utf-8") as hf:
                        lines = hf.readlines()
                        if lines:
                            for line in lines:
                                data = json.loads(line.strip())
                                # 에이전트(assistant)의 새로운 메시지이고, 이전에 처리하지 않은 것이라면
                                if data.get("role") == "assistant" and data.get("ts") > last_agent_ts:
                                    reply_text = data.get("text", "")
                                    print(f"[{time.strftime('%H:%M:%S')}] 에이전트 응답 발견: {reply_text[:20]}...")
                                    
                                    # 텔레그램으로 전송
                                    requests.post(
                                        f"https://api.telegram.org/bot{token}/sendMessage",
                                        json={"chat_id": chat, "text": f"🤖 [에이전트]: {reply_text}"},
                                    )
                                    last_agent_ts = data.get("ts")
            except Exception as e:
                print(f"⚠️ 에이전트 답변 확인 실패: {e}")
                
            time.sleep(2) # CPU 과부하 방지 및 체크 주기
            
    except KeyboardInterrupt:
        print("\n👋 메시지 수신을 종료합니다.")

if __name__ == "__main__":
    main()
