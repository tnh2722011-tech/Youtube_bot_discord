import requests, time, json, random, sys, os
import websocket
from threading import Thread
from datetime import datetime

class Color:
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    END = '\033[0m'
    BLUE = '\033[94m'

class UltraBattle:
    def __init__(self, token):
        self.token = token
        self.headers = {'Authorization': token, 'Content-Type': 'application/json'}
        self.mimi_id = "1207923287519268875"
        self.own_id = None
        self.username = "Unknown"
        
        self.is_running = False
        self.active_channel = None
        self.stats = {"battle": 0, "stamina_used": 0}
        self.logs = []

        if self._get_user_info():
            self.add_log(f"Đã đăng nhập: {self.username}")
            self._start_gateway()

    def _get_user_info(self):
        try:
            res = requests.get("https://discord.com/api/v9/users/@me", headers=self.headers)
            if res.status_code == 200:
                data = res.json()
                self.own_id, self.username = data['id'], data['username']
                return True
        except: return False
        return False

    def add_log(self, text):
        now = datetime.now().strftime("%H:%M:%S")
        self.logs.append(f"[{now}] {text[:50]}")
        self._update_dashboard()

    def _update_dashboard(self):
        os.system('clear')
        status = f"{Color.GREEN}ĐANG CHẠY{Color.END}" if self.is_running else f"{Color.RED}ĐANG DỪNG{Color.END}"
        print(f"{Color.CYAN}{Color.BOLD} ⚔️ DISCORD AUTO BATTLE v1.0 ⚔️ {Color.END}")
        print(f"👤 User: {Color.BOLD}{self.username}{Color.END} | Trạng thái: {status}")
        print(f"📊 Battle: {self.stats['battle']} | Stamina: {self.stats['stamina_used']}")
        print(f"{Color.BLUE}--------------------------------------------------{Color.END}")
        for log in self.logs[-6:]: print(f" {log}")
        print(f"{Color.BLUE}--------------------------------------------------{Color.END}")
        print(f"{Color.YELLOW}Dùng ',play' để bắt đầu | ',stop' để dừng (trong Discord){Color.END}")

    def _send_msg(self, channel_id, content):
        try:
            # Cơ chế Fake Soạn (Typing)
            requests.post(f"https://discord.com/api/v9/channels/{channel_id}/typing", headers=self.headers)
            # Thời gian soạn tin ngẫu nhiên 
            time.sleep(random.uniform(0.5, 1.0))
            
            res = requests.post(f"https://discord.com/api/v9/channels/{channel_id}/messages", 
                                headers=self.headers, json={"content": content})
            return res.status_code == 200
        except: return False

    def _battle_loop(self, channel_id):
        """Vòng lặp gửi .battle mỗi 40 giây"""
        while self.is_running and self.active_channel == channel_id:
            if self._send_msg(channel_id, ".battle"):
                self.stats['battle'] += 1
                self.add_log(f"Đã gửi .battle (Lần {self.stats['battle']})")
                # Chờ 40s cho lượt tiếp theo
                for _ in range(40):
                    if not self.is_running or self.active_channel != channel_id: break
                    time.sleep(1)
            else:
                self.add_log(f"{Color.RED}Lỗi mạng! Đóng băng 10s...{Color.END}")
                time.sleep(10)

    def on_message(self, msg):
        d = msg.get('d', {})
        content = d.get('content', '')
        author_id = d.get('author', {}).get('id')
        channel_id = d.get('channel_id')

        # Lệnh điều khiển
        if author_id == self.own_id:
            if content == ",play":
                if not self.is_running:
                    self.is_running = True
                    self.active_channel = channel_id
                    Thread(target=self._battle_loop, args=(channel_id,), daemon=True).start()
                    self.add_log("Kích hoạt Auto Battle!")
            elif content == ",stop":
                self.is_running = False
                self.active_channel = None
                self.add_log("Đã dừng Battle.")

        # Quét tin nhắn từ Mimi (Chỉ quét trong channel đang chạy)
        if author_id == self.mimi_id and self.is_running and channel_id == self.active_channel:
            
            # Kiểm tra xem có phải Mimi đang trả lời mình không
            is_reply_to_me = False
            if 'referenced_message' in d and d['referenced_message'] is not None:
                if d['referenced_message'].get('author', {}).get('id') == self.own_id:
                    is_reply_to_me = True
            
            # Kiểm tra Mention
            if not is_reply_to_me:
                for user in d.get('mentions', []):
                    if user.get('id') == self.own_id:
                        is_reply_to_me = True

            if is_reply_to_me:
                # Cập nhật logic: Chỉ cần thấy "Không đủ thể lực" là xử lý ngay
                if "Không đủ thể lực" in content:
                    self.add_log(f"{Color.YELLOW}Phát hiện hết thể lực! Đang soạn tin hồi phục...{Color.END}")
                    if self._send_msg(channel_id, ".use STAMINA-S"):
                        self.stats['stamina_used'] += 1
                        self.add_log("Đã sử dụng Bình Thể Lực (S)")

    def _start_gateway(self):
        while True:
            try:
                ws = websocket.WebSocket()
                ws.connect("wss://gateway.discord.gg/?v=9&encoding=json")
                ws.send(json.dumps({
                    "op": 2,
                    "d": {
                        "token": self.token,
                        "properties": {"os": "android", "browser": "Discord Android", "device": "Xiaomi"}
                    }
                }))

                while True:
                    result = ws.recv()
                    if not result: break
                    res = json.loads(result)
                    if res.get('op') == 10:
                        interval = res['d']['heartbeat_interval'] / 1000
                        Thread(target=self._heartbeat, args=(ws, interval), daemon=True).start()
                    if res.get('t') == "MESSAGE_CREATE":
                        self.on_message(res)
            except Exception:
                self.add_log(f"{Color.RED}Mất kết nối! Reconnect sau 5s...{Color.END}")
                time.sleep(5)

    def _heartbeat(self, ws, interval):
        while True:
            try:
                time.sleep(interval)
                ws.send(json.dumps({"op": 1, "d": None}))
            except: break

if __name__ == "__main__":
    os.system('clear')
    print(f"{Color.CYAN}--- DISCORD TOOL SETUP ---{Color.END}")
    tk = input(f"Nhập Token User: ").strip()
    UltraBattle(tk)
    