import sqlite3, requests, urllib3, uuid, time, re, json, enum, os
from typing import Optional

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

GIGA_AUTH_KEY = " "
DB_PATH = "slots.db"

CLIENTS = [
    {
        "id": 0,
        "name": "Иванов Сергей Петрович",
        "address": "г. Москва, ул. Тверская, д. 12",
        "date": "17 марта",
        "slot": "10:00–12:00",
    },
    {
        "id": 1,
        "name": "Смирнова Елена Владимировна",
        "address": "г. Москва, ул. Арбат, д. 25",
        "date": "17 марта",
        "slot": "10:00–12:00",
    },
    {
        "id": 2,
        "name": "Кузнецов Андрей Николаевич",
        "address": "г. Москва, Ленинский проспект, д. 40",
        "date": "17 марта",
        "slot": "12:00–14:00",
    },
    {
        "id": 3,
        "name": "Попова Марина Александровна",
        "address": "г. Москва, ул. Профсоюзная, д. 65",
        "date": "17 марта",
        "slot": "12:00–14:00",
    },
    {
        "id": 4,
        "name": "Новиков Дмитрий Игоревич",
        "address": "г. Москва, Проспект Мира, д. 80",
        "date": "17 марта",
        "slot": "14:00–16:00",
    },
]

ALL_DATES = ["18 марта", "19 марта", "20 марта", "21 марта", "22 марта"]
ALL_TIMES = ["10:00–12:00", "12:00–14:00", "14:00–16:00", "16:00–18:00"]


# ══════════════════════════════════════════════════════════════
#  БАЗА СЛОТОВ
# ══════════════════════════════════════════════════════════════


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS slots (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            date      TEXT NOT NULL,
            slot      TEXT NOT NULL,
            status    TEXT NOT NULL DEFAULT 'FREE',
            client_id INTEGER,
            UNIQUE(date, slot)
        )
    """
    )
    for d in ALL_DATES:
        for t in ALL_TIMES:
            c.execute(
                "INSERT OR IGNORE INTO slots (date, slot, status) VALUES (?, ?, 'FREE')",
                (d, t),
            )
    conn.commit()
    conn.close()
    print(f"  [DB] База слотов инициализирована: {DB_PATH}")


class AvailabilityService:

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def find_slots(
        self, preference: dict, limit: int = 3, exclude_slots: list[dict] | None = None
    ) -> list[dict]:
        """
        Возвращает до limit свободных слотов под предпочтение.
        exclude_slots — пары {date, slot} которые уже показывали клиенту,
        чтобы при повторном поиске не предлагать то же самое.
        """
        period = preference.get("period", "any")
        slot_filter = {
            "morning": ["10:00–12:00"],
            "afternoon": ["12:00–14:00", "14:00–16:00"],
            "evening": ["16:00–18:00"],
            "any": ALL_TIMES,
        }.get(period, ALL_TIMES)

        if preference.get("date"):
            idx = (
                ALL_DATES.index(preference["date"])
                if preference["date"] in ALL_DATES
                else 0
            )
            search_dates = ALL_DATES[idx:]
        elif preference.get("not_before_date"):
            idx = (
                ALL_DATES.index(preference["not_before_date"])
                if preference["not_before_date"] in ALL_DATES
                else 0
            )
            search_dates = ALL_DATES[idx:]
        elif preference.get("dates"):
            search_dates = [d for d in preference["dates"] if d in ALL_DATES]
        else:
            search_dates = ALL_DATES

        excluded = {(s["date"], s["slot"]) for s in (exclude_slots or [])}

        results = []
        conn = self._conn()
        c = conn.cursor()
        for d in search_dates:
            for s in slot_filter:
                if (d, s) in excluded:
                    continue
                c.execute(
                    "SELECT date, slot FROM slots WHERE date=? AND slot=? AND status='FREE'",
                    (d, s),
                )
                row = c.fetchone()
                if row:
                    results.append({"date": row[0], "slot": row[1]})
                    if len(results) >= limit:
                        break
            if len(results) >= limit:
                break
        conn.close()
        return results

    def hold(self, date: str, slot: str, client_id: int) -> bool:
        conn = self._conn()
        c = conn.cursor()
        c.execute(
            "UPDATE slots SET status='HOLD', client_id=? WHERE date=? AND slot=? AND status='FREE'",
            (client_id, date, slot),
        )
        ok = c.rowcount > 0
        conn.commit()
        conn.close()
        return ok

    def confirm(self, date: str, slot: str, client_id: int) -> bool:
        conn = self._conn()
        c = conn.cursor()
        c.execute(
            "UPDATE slots SET status='BOOKED' WHERE date=? AND slot=? AND client_id=? AND status='HOLD'",
            (date, slot, client_id),
        )
        ok = c.rowcount > 0
        conn.commit()
        conn.close()
        return ok

    def release(self, client_id: int):
        """Снимает ВСЕ HOLD клиента — вызывается при любом завершении."""
        conn = self._conn()
        c = conn.cursor()
        c.execute(
            "UPDATE slots SET status='FREE', client_id=NULL WHERE client_id=? AND status='HOLD'",
            (client_id,),
        )
        conn.commit()
        conn.close()

    def print_status(self):
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT date, slot, status, client_id FROM slots ORDER BY date, slot")
        rows = c.fetchall()
        conn.close()
        print("\n  [DB STATUS]")
        print(f"  {'Дата':<12} {'Слот':<15} {'Статус':<8} {'Клиент'}")
        print("  " + "-" * 50)
        for r in rows:
            name = next(
                (cl["name"].split()[0] for cl in CLIENTS if cl["id"] == r[3]), ""
            )
            print(f"  {r[0]:<12} {r[1]:<15} {r[2]:<8} {name}")


# ══════════════════════════════════════════════════════════════
#  FSM
# ══════════════════════════════════════════════════════════════


class State(enum.Enum):
    AWAIT_CONFIRM = "AWAIT_CONFIRM"
    AWAIT_FINAL_REJECT = "AWAIT_FINAL_REJECT"
    AWAIT_SLOT_CHOICE = "AWAIT_SLOT_CHOICE"  
    AWAIT_SLOT_CONFIRM = "AWAIT_SLOT_CONFIRM" 
    AWAIT_SLOT_CLARIFY = (
        "AWAIT_SLOT_CLARIFY" 
    )
    FINISHED = "FINISHED"


STATE_INTENTS = {
    State.AWAIT_CONFIRM: [
        "CONFIRM", 
        "REJECT",  
        "RESCHEDULE",  
        "NOT_ORDERED",  
        "RUDE",  
        "OFFTOPIC",  
        "UNCLEAR",
    ],
    State.AWAIT_FINAL_REJECT: [
        "CONFIRM",  
        "CANCEL",  
        "RESCHEDULE", 
        "UNCLEAR",
    ],
    State.AWAIT_SLOT_CHOICE: [
        "SLOT_CHOSEN", 
        "REJECT_SLOTS",  
        "CANCEL", 
        "CONFIRM", 
        "UNCLEAR",
    ],
    State.AWAIT_SLOT_CONFIRM: [
        "CONFIRM",  
        "REJECT_SLOTS", 
        "CANCEL",  
        "UNCLEAR",
    ],
    State.AWAIT_SLOT_CLARIFY: [
        "SLOT_CHOSEN",  
        "CANCEL",  
        "UNCLEAR",
    ],
}

STATE_REPEAT_QUESTION = {
    State.AWAIT_CONFIRM: "Вы подтверждаете получение карты?",
    State.AWAIT_FINAL_REJECT: "Доставить карту или отменить?",
    State.AWAIT_SLOT_CHOICE: "Какой из вариантов Вам подходит — первый, второй или третий?",
    State.AWAIT_SLOT_CONFIRM: "Вам подходит предложенное время?",
    State.AWAIT_SLOT_CLARIFY: "Уточните, пожалуйста, — какой вариант: первый, второй или третий?",
}

TEMPLATES = {
    "T_CONFIRM": "Отлично. Контакты менеджера будут направлены дополнительно. Хорошего дня!",
    "T_CANCEL": "Принято. Доставка отменена. Если Вы измените решение — обращайтесь в СберБизнес. Хорошего дня!",
    "T_NOT_ORDERED": "Приношу извинения за беспокойство. Информацию передам специалистам для уточнения. Хорошего дня!",
    "T_RESCHEDULE_DONE": "Отлично, перенос оформлен! Карта будет доставлена {date} в период {slot}. Контакты менеджера будут направлены дополнительно. Хорошего дня!",
    "T_REJECT_FIRST": "Очень жаль. Мы можем отменить доставку. Но прежде — безналичные операции без комиссии, индивидуальные лимиты, первый год обслуживания бесплатно. Доставить Вам выпущенную на Ваше имя карту?",
    "T_SLOTS_OFFER": "Для Вас доступны следующие варианты: {options}. Какой удобен?",
    "T_SLOT_SINGLE": "Ближайший доступный вариант — {date} в период {slot}. Вам подходит?",
    "T_NO_SLOTS": "К сожалению, свободных слотов по Вашему запросу нет. Могу предложить любое доступное время — рассмотрите?",
    "T_RUDE": "Понимаю Вашу реакцию. Постараюсь быть краток. Вы подтверждаете получение карты?",
    "T_OFFTOPIC": "По данному вопросу рекомендую обратиться на горячую линию СберБизнеса. Итак, Вы подтверждаете получение карты завтра?",
    "T_UNCLEAR": "Прошу прощения, не расслышал. {repeat_question}",
    "T_CLARIFY_CHOICE": "Уточните, пожалуйста — какой вариант Вам удобен: {options}?",
}


def first_name_patronymic(full_name: str) -> str:
    parts = full_name.strip().split()
    return f"{parts[1]} {parts[2]}" if len(parts) >= 3 else full_name


# ══════════════════════════════════════════════════════════════
#  LLM: ТОЛЬКО NLU
# ══════════════════════════════════════════════════════════════

class GigaChatLLM:
    def __init__(self):
        self.token = None
        self.expires = 0

    def _refresh(self):
        try:
            r = requests.post(
                "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
                headers={
                    "Authorization": f"Basic {GIGA_AUTH_KEY}",
                    "RqUID": str(uuid.uuid4()),
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={"scope": "GIGACHAT_API_PERS"},
                verify=False,
                timeout=10,
            )
            if r.status_code == 200:
                j = r.json()
                self.token = j["access_token"]
                self.expires = j["expires_at"] / 1000
        except Exception as e:
            print(f"  [token error] {e}")

    def _call(self, system: str, user: str, max_tokens: int = 80) -> str:
        if time.time() > self.expires - 60:
            self._refresh()
        if not self.token:
            return ""
        try:
            r = requests.post(
                "https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "GigaChat",
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0.0,
                    "max_tokens": max_tokens,
                },
                verify=False,
                timeout=5,
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
        except:
            pass
        return ""

    def _parse_json(self, raw: str) -> dict:
        for m in reversed(re.findall(r"\{[^{}]+\}", raw, re.DOTALL)):
            try:
                return json.loads(m)
            except:
                pass
        return {}

    def classify(self, user_text: str, state: State) -> str:
        allowed = STATE_INTENTS[state]
        allowed_str = ", ".join(allowed)

        descriptions = {
            "CONFIRM": "клиент соглашается / говорит да / передумал / хочет карту / оставить как было",
            "REJECT": "клиент отказывается впервые (нет, не нужно, не хочу)",
            "CANCEL": "клиент окончательно отказывается / просит отменить доставку полностью",
            "RESCHEDULE": "клиент просит перенести на другой день или время",
            "NOT_ORDERED": "клиент говорит что не заказывал эту карту",
            "RUDE": "клиент груб, раздражён, недоволен звонком",
            "OFFTOPIC": "вопрос не по теме доставки (кэшбэк, тарифы и т.д.)",
            "SLOT_CHOSEN": "клиент выбирает конкретный вариант из предложенных: называет номер (1,2,3), дату или время",
            "REJECT_SLOTS": "клиент говорит что предложенные варианты не подходят / хочет другое время / не устраивает",
            "UNCLEAR": "непонятная реплика, невозможно определить намерение",
        }
        desc_str = "\n".join(
            f"- {i}: {descriptions[i]}" for i in allowed if i in descriptions
        )

        system = f"""Ты — NLU-классификатор голосового робота СберБизнеса.
Определи интент реплики клиента. Доступные интенты: {allowed_str}

{desc_str}

Верни СТРОГО JSON без лишнего текста: {{"intent": "INTENT"}}"""

        raw = self._call(system, user_text, max_tokens=50)
        intent = self._parse_json(raw).get("intent", "UNCLEAR").upper()
        return intent if intent in [i.upper() for i in allowed] else "UNCLEAR"

    def extract_preference(self, user_text: str) -> dict:
        system = """Ты извлекаешь предпочтения клиента по дате и времени доставки.
Доступные даты: "18 марта", "19 марта", "20 марта", "21 марта", "22 марта". 
Текстовые даты ("18-е", "восемнадцатое", "завтра") приводи к правильному формату.
Периоды дня: morning (10:00–12:00), afternoon (12:00–16:00), evening (16:00–18:00), any.

Верни СТРОГО JSON:
{"date": "19 марта" или null, "period": "morning"|"afternoon"|"evening"|"any", "not_before_date": "20 марта" или null}"""
        
        raw = self._call(system, user_text, max_tokens=80)
        parsed = self._parse_json(raw)
        valid_dates = ALL_DATES + [None]
        valid_periods = ["morning", "afternoon", "evening", "any"]
        return {
            "date": parsed.get("date") if parsed.get("date") in valid_dates else None,
            "period": (
                parsed.get("period", "any")
                if parsed.get("period") in valid_periods
                else "any"
            ),
            "not_before_date": (
                parsed.get("not_before_date")
                if parsed.get("not_before_date") in valid_dates
                else None
            ),
        }
    def identify_chosen_slot(self, user_text: str, offered_slots: list[dict]) -> Optional[dict]:
        if not offered_slots:
            return None
        slots_str = "\n".join(
            f"{i+1}. {s['date']} {s['slot']}" for i, s in enumerate(offered_slots)
        )
        system = f"""Клиенту предложены варианты:
{slots_str}

Реплика клиента: "{user_text}"
Определи, какой вариант он выбрал (по номеру, слову "первый"/"второй" или по времени).
Верни СТРОГО JSON без лишних слов: {{"choice": 1}} (где цифра — номер варианта из списка).
Если вариант не назван или непонятен, верни {{"choice": 0}}."""

        raw = self._call(system, user_text, max_tokens=30)
        choice = self._parse_json(raw).get("choice", 0)
        if isinstance(choice, int) and 1 <= choice <= len(offered_slots):
            return offered_slots[choice - 1]
        return None

# ══════════════════════════════════════════════════════════════
#  DIALOG MANAGER
# ══════════════════════════════════════════════════════════════

class DialogManager:
    def __init__(
        self, client: dict, llm: GigaChatLLM, availability: AvailabilityService
    ):
        self.client = client
        self.llm = llm
        self.availability = availability
        self.state = State.AWAIT_CONFIRM
        self.context = {
            "unclear_count": 0,
            "offered_slots": [],  
            "shown_slots": [],  
            "chosen_slot": None,
            "was_rude": False,
            "last_preference": {},
        }
        self.metrics = {
            "total_time": 0,
            "turns": 0,
            "fallbacks": 0,
            "status": "В ПРОЦЕССЕ",
        }

    def _fmt(self, key: str, **kw) -> str:
        return TEMPLATES[key].format(**kw)

    def _finish(self, status: str, reply_key: str, **kw) -> str:
        self.state = State.FINISHED
        self.metrics["status"] = status
        self.availability.release(self.client["id"])  
        return self._fmt(reply_key, **kw)

    def _hold_slots(self, slots: list[dict]):
        held = []
        for s in slots:
            if self.availability.hold(s["date"], s["slot"], self.client["id"]):
                held.append(s)
        self.context["offered_slots"] = held
        self.context["shown_slots"].extend(held)

    def _release_offered(self):
        self.availability.release(self.client["id"])
        self.context["offered_slots"] = []

    def _offer_slots(self, preference: dict) -> str:
        """Ищет слоты с учётом уже показанных, ставит hold, формирует реплику."""
        self.context["last_preference"] = preference

        slots = self.availability.find_slots(
            preference,
            limit=3,
            exclude_slots=self.context["shown_slots"],
        )

        if not slots and preference.get("period", "any") != "any":
            slots = self.availability.find_slots(
                {**preference, "period": "any"},
                limit=3,
                exclude_slots=self.context["shown_slots"],
            )

        if not slots:
            self.state = State.AWAIT_SLOT_CONFIRM
            self.context["offered_slots"] = [] 
            return self._fmt("T_NO_SLOTS")

        self._hold_slots(slots)

        if len(slots) == 1:
            self.state = State.AWAIT_SLOT_CONFIRM
            return self._fmt(
                "T_SLOT_SINGLE", date=slots[0]["date"], slot=slots[0]["slot"]
            )
        else:
            self.state = State.AWAIT_SLOT_CHOICE
            options = " | ".join(
                f"{i+1}) {s['date']} {s['slot']}" for i, s in enumerate(slots)
            )
            return self._fmt("T_SLOTS_OFFER", options=options)

    def start_call(self) -> str:
        fname = first_name_patronymic(self.client["name"])
        reply = (
            f"Добрый день, {fname}! Завтра, {self.client['date']}, "
            f"по адресу {self.client['address']}, в период {self.client['slot']} "
            f"Вам запланирована доставка бизнес-карты СберБизнеса. "
            f"Вы подтверждаете получение карты по данному адресу?"
        )
        self.metrics["turns"] += 1
        print(f"   🤖 [GREETING]: {reply}")
        return reply
    def _pre_classify(self, user_text: str, state: State) -> Optional[str]:
        t_clean = re.sub(r'[^\w\s]', '', user_text.lower()).strip()

        if t_clean == "да":
            return "CONFIRM"
        if t_clean == "нет":
            if state == State.AWAIT_CONFIRM: return "REJECT"
            if state == State.AWAIT_FINAL_REJECT: return "CANCEL"
            if state in (State.AWAIT_SLOT_CONFIRM, State.AWAIT_SLOT_CHOICE): return "REJECT_SLOTS"

        if re.match(r'^[123]$', t_clean):
            if state in (State.AWAIT_SLOT_CHOICE, State.AWAIT_SLOT_CLARIFY, State.AWAIT_SLOT_CONFIRM):
                return "SLOT_CHOSEN"

        return None 
    def process_turn(self, user_text: str) -> str:
        t0 = time.time()

        intent = self._pre_classify(user_text, self.state)
        source = "RULE"

        if intent is None:
            intent = self.llm.classify(user_text, self.state)
            source = "LLM"

        reply = self._transition(intent, user_text)
        elapsed = time.time() - t0
        self.metrics["turns"] += 1
        self.metrics["total_time"] += elapsed

        print(f"   🤖 [{source}:{intent}→{self.state.name}]: {reply}")
        return reply
    
    def _transition(self, intent: str, user_text: str) -> str:

        # ── AWAIT_CONFIRM ───────────────────────────────────────
        if self.state == State.AWAIT_CONFIRM:
            if intent == "CONFIRM":
                return self._finish("✅ ПОДТВЕРЖДЕНО", "T_CONFIRM")

            elif intent == "REJECT":
                if self.context["was_rude"]:
                    return self._finish("❌ ОТМЕНЕНО", "T_CANCEL")
                self.state = State.AWAIT_FINAL_REJECT
                return self._fmt("T_REJECT_FIRST")

            elif intent == "RESCHEDULE":
                pref = self.llm.extract_preference(user_text)
                return self._offer_slots(pref)

            elif intent == "NOT_ORDERED":
                return self._finish("⚠️ НЕ ЗАКАЗЫВАЛ", "T_NOT_ORDERED")

            elif intent == "RUDE":
                self.context["was_rude"] = True
                return self._fmt("T_RUDE")

            elif intent == "OFFTOPIC":
                return self._fmt("T_OFFTOPIC")

            else:
                return self._handle_unclear()

        # ── AWAIT_FINAL_REJECT ──────────────────────────────────
        elif self.state == State.AWAIT_FINAL_REJECT:
            if intent == "CONFIRM":
                return self._finish("✅ ПОДТВЕРЖДЕНО", "T_CONFIRM")

            elif intent == "CANCEL":
                return self._finish("❌ ОТМЕНЕНО", "T_CANCEL")

            elif intent == "RESCHEDULE":
                pref = self.llm.extract_preference(user_text)
                return self._offer_slots(pref)

            else:
                return self._handle_unclear()

        # ── AWAIT_SLOT_CHOICE: показали 2-3 варианта ───────────
        elif self.state == State.AWAIT_SLOT_CHOICE:
            if intent == "SLOT_CHOSEN":
                chosen = self.llm.identify_chosen_slot(
                    user_text, self.context["offered_slots"]
                )
                if chosen:
                    self._release_offered()
                    self.availability.hold(
                        chosen["date"], chosen["slot"], self.client["id"]
                    )
                    self.availability.confirm(
                        chosen["date"], chosen["slot"], self.client["id"]
                    )
                    return self._finish(
                        "🔄 ПЕРЕНЕСЕНО",
                        "T_RESCHEDULE_DONE",
                        date=chosen["date"],
                        slot=chosen["slot"],
                    )
                self.state = State.AWAIT_SLOT_CLARIFY
                options = " | ".join(
                    f"{i+1}) {s['date']} {s['slot']}"
                    for i, s in enumerate(self.context["offered_slots"])
                )
                return self._fmt("T_CLARIFY_CHOICE", options=options)

            elif intent == "REJECT_SLOTS":
                self._release_offered()
                pref = self.context.get("last_preference") or {"period": "any"}
                return self._offer_slots(pref)

            elif intent == "CONFIRM":
                self.state = State.AWAIT_SLOT_CLARIFY
                options = " | ".join(
                    f"{i+1}) {s['date']} {s['slot']}"
                    for i, s in enumerate(self.context["offered_slots"])
                )
                return self._fmt("T_CLARIFY_CHOICE", options=options)

            elif intent == "CANCEL":
                self._release_offered()
                return self._finish("❌ ОТМЕНЕНО", "T_CANCEL")

            else:
                return self._handle_unclear()

        elif self.state == State.AWAIT_SLOT_CONFIRM:
            if intent == "CONFIRM":
                slots = self.context["offered_slots"]
                if slots:
                    self.availability.confirm(
                        slots[0]["date"], slots[0]["slot"], self.client["id"]
                    )
                    return self._finish(
                        "🔄 ПЕРЕНЕСЕНО",
                        "T_RESCHEDULE_DONE",
                        date=slots[0]["date"],
                        slot=slots[0]["slot"],
                    )
                else:
                    return self._offer_slots({"period": "any"})
                
                
        # ── AWAIT_SLOT_CLARIFY: уточняем номер ──────────────────
        elif self.state == State.AWAIT_SLOT_CLARIFY:
            if intent == "SLOT_CHOSEN":
                chosen = self.llm.identify_chosen_slot(
                    user_text, self.context["offered_slots"]
                )
                if chosen:
                    self._release_offered()
                    self.availability.hold(
                        chosen["date"], chosen["slot"], self.client["id"]
                    )
                    self.availability.confirm(
                        chosen["date"], chosen["slot"], self.client["id"]
                    )
                    return self._finish(
                        "🔄 ПЕРЕНЕСЕНО",
                        "T_RESCHEDULE_DONE",
                        date=chosen["date"],
                        slot=chosen["slot"],
                    )
                return self._handle_unclear()

            elif intent == "CANCEL":
                self._release_offered()
                return self._finish("❌ ОТМЕНЕНО", "T_CANCEL")

            else:
                return self._handle_unclear()

        return "Хорошего дня!"

    def _handle_unclear(self) -> str:
        self.context["unclear_count"] += 1
        self.metrics["fallbacks"] += 1
        if self.context["unclear_count"] >= 3:
            self.state = State.FINISHED
            self.metrics["status"] = "⛔ ЗАВЕРШЕНО (нет связи)"
            self.availability.release(self.client["id"])
            return "Прошу прощения, похоже возникли проблемы со связью. Перезвоним Вам позже. Хорошего дня!"
        repeat = STATE_REPEAT_QUESTION.get(self.state, "Повторите, пожалуйста?")
        return self._fmt("T_UNCLEAR", repeat_question=repeat)


# ══════════════════════════════════════════════════════════════
#  СЦЕНАРИИ  (все 10 с полными репликами)
# ══════════════════════════════════════════════════════════════

SCENARIOS = [
    {
        "name": "1. Хэппи-пас",
        "ci": 0,
        "lines": ["Да, подтверждаю."],
        "expected": "✅ ПОДТВЕРЖДЕНО",
    },
    {
        "name": "2. Двойной отказ → Отмена",
        "ci": 1,
        "lines": [
            "Нет, не нужно.",
            "Нет, я работаю с другим банком.",
        ],
        "expected": "❌ ОТМЕНЕНО",
    },
    {
        "name": "3. Конфликт слотов: первый занимает 19 марта утром",
        "ci": 2,
        "lines": [
            "Перенесите на 19 марта, лучше утром.",
            "Первый вариант, пожалуйста.",          
        ],
        "expected": "🔄 ПЕРЕНЕСЕНО",
    },
    {
        "name": "4. Конфликт слотов: второй клиент — другой слот",
        "ci": 3,
        "lines": [
            "Хочу перенести на 19 марта, утром если можно.",
            "Да, давайте.",
            "Давайте первый."  
        ],
        "expected": "🔄 ПЕРЕНЕСЕНО",
    },
    {
        "name": "5. Не заказывал",
        "ci": 2,
        "lines": ["Я эту карту вообще не запрашивал!"],
        "expected": "⚠️ НЕ ЗАКАЗЫВАЛ",
    },
    {
        "name": "6. Оффтоп + гибкий перенос (конец недели, вечером)",
        "ci": 3,
        "lines": [
            "А какой кэшбэк на ней?",
            "Ладно, перенесите на конец недели, желательно вечером.",
            "Да, подходит.",
        ],
        "expected": "🔄 ПЕРЕНЕСЕНО",
    },
    {
        "name": "7. Грубость → Отмена",
        "ci": 4,
        "lines": [
            "Какой еще курьер, вы достали!",
            "Ладно, просто отмените.",
        ],
        "expected": "❌ ОТМЕНЕНО",
    },
    {
        "name": "8. Перенос → выбор словом",
        "ci": 0,
        "lines": [
            "Завтра не могу, перенесём.",
            "Второй вариант мне удобен.",            
        ],
        "expected": "🔄 ПЕРЕНЕСЕНО",
    },
    {
        "name": "9. Слоты не подошли → следующая пачка → выбирает",
        "ci": 1,
        "lines": [
            "Перенесите пожалуйста.",
            "Нет, это время не подходит, другое предложите.",
            "Первый подходит, давайте его.",       
        ],
        "expected": "🔄 ПЕРЕНЕСЕНО",
    },
    {
        "name": "10. Отказ → преимущества → перенос → выбор слота",
        "ci": 4,
        "lines": [
            "Нет, не нужно.",
            "Хм, бесплатно первый год? Давайте тогда перенесём на 20-е.",
            "Мне удобно с десяти до двенадцати.",
            "Да, подходит."
        ],
        "expected": "🔄 ПЕРЕНЕСЕНО",
    },
]

# ══════════════════════════════════════════════════════════════
#  ЗАПУСК
# ══════════════════════════════════════════════════════════════

def run():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_db()

    llm = GigaChatLLM()
    avail = AvailabilityService()

    print("\n" + "🚀 " * 18)
    print("  СБЕРБИЗНЕС — v10.1  |  FSM + LLM-NLU + REAL-TIME SLOTS")
    print("🚀 " * 18 + "\n")

    results = []
    passed = 0

    for sc in SCENARIOS:
        c = CLIENTS[sc["ci"]]
        print("━" * 60)
        print(f"  {sc['name']} | Клиент: {c['name']}")
        print("━" * 60)

        dm = DialogManager(c, llm, avail)
        dm.start_call()

        for line in sc["lines"]:
            if dm.state == State.FINISHED:
                break
            print(f"   👤: {line}")
            dm.process_turn(line)

        m = dm.metrics
        status = m["status"]
        expected = sc.get("expected", "")
        ok = expected in status if expected else True
        passed += int(ok)
        badge = "✅" if ok else "❌ ОЖИДАЛОСЬ: " + expected

        print(
            f"\n  ➤ {badge} | Итог: {status} | Реплик: {m['turns']} | Фоллбэки: {m['fallbacks']} | Время: {m['total_time']:.1f}s\n"
        )
        results.append(
            {
                "status": status,
                "turns": m["turns"],
                "fallbacks": m["fallbacks"],
                "aht": m["total_time"],
            }
        )

    avail.print_status()

    total = len(results)
    confirmed = sum(
        1
        for r in results
        if any(s in r["status"] for s in ["ПОДТВЕРЖДЕНО", "ПЕРЕНЕСЕНО"])
    )
    canceled = sum(1 for r in results if "ОТМЕНЕНО" in r["status"])
    errors = sum(
        1 for r in results if "В ПРОЦЕССЕ" in r["status"] or "ЗАВЕРШЕНО" in r["status"]
    )

    print("\n" + "=" * 60)
    print("  📊 ДАШБОРД ИТОГОВ")
    print("=" * 60)
    print(f"  Тестов пройдено:             {passed}/{total}")
    print(f"  Conversation Rate (CR):      {(confirmed/total)*100:.1f}%")
    print(f"  Cancellation Rate:           {(canceled/total)*100:.1f}%")
    print(f"  Drop/Loop Rate (Сбои):       {(errors/total)*100:.1f}%")
    print(
        f"  Avg Turns (Реплик/диалог):   {sum(r['turns'] for r in results)/total:.1f}"
    )
    print(
        f"  Avg AHT (Время диалога):     {sum(r['aht'] for r in results)/total:.1f} сек"
    )
    print(f"  Total Fallbacks (Сбои LLM):  {sum(r['fallbacks'] for r in results)}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    run()
