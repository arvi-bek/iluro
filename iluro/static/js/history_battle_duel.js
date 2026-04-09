(function () {
    const board = document.querySelector(".battle-board");
    if (!board) return;

    const storageKey = "iluro-history-battle-setup";
    const questionUrl = board.dataset.questionUrl;
    const initialGrade = board.dataset.selectedGrade || "";
    const gradeOptions = JSON.parse(document.getElementById("history-battle-grade-options")?.textContent || "[]");
    const MATCH_DURATION_SECONDS = 180;
    const QUESTION_BATCH_SIZE = 30;
    const LOW_WATERMARK_PAIRS = 4;
    const FRONTLINE_TARGET = 5;
    const POINTS_PER_CORRECT = 2;
    const RESOLVE_DELAY_MS = 900;

    const $ = (id) => document.getElementById(id);
    const els = {
        overlay: $("battle-setup-overlay"),
        gradeCards: Array.from(document.querySelectorAll(".game-grade-card")),
        teamOneInput: $("battle-team-one-input"),
        teamTwoInput: $("battle-team-two-input"),
        startButton: $("battle-start-btn"),
        configButton: $("battle-configure-btn"),
        banner: $("battle-banner"),
        status: $("battle-status"),
        progress: $("battle-progress"),
        roundLabel: $("battle-round-label"),
        timer: $("battle-timer"),
        scoreLeft: $("battle-player-score"),
        scoreRight: $("battle-bot-score"),
        miniLeft: $("battle-left-mini-score"),
        miniRight: $("battle-right-mini-score"),
        leftQuestion: $("battle-left-question-text"),
        rightQuestion: $("battle-right-question-text"),
        leftOptions: $("battle-left-options"),
        rightOptions: $("battle-right-options"),
        leftGrade: $("battle-grade-badge"),
        rightGrade: $("battle-right-grade-badge"),
        leftSource: $("battle-left-source-badge"),
        rightSource: $("battle-right-source-badge"),
        topbarGrade: $("battle-topbar-grade"),
        topbarCount: $("battle-topbar-count"),
        teamOneName: $("battle-team-one-name"),
        teamTwoName: $("battle-team-two-name"),
        teamOneMeta: $("battle-team-one-meta"),
        teamTwoMeta: $("battle-team-two-meta"),
        leftLabel: $("battle-left-label"),
        rightLabel: $("battle-right-label"),
        leftIconLabel: $("battle-left-icon-label"),
        rightIconLabel: $("battle-right-icon-label"),
        log: $("battle-log"),
    };

    const state = {
        grade: "",
        gradeLabel: "Tarix",
        pairs: [],
        roundIndex: 0,
        leftScore: 0,
        rightScore: 0,
        frontline: 0,
        leftName: "1-jamoa",
        rightName: "2-jamoa",
        leftAnswer: null,
        rightAnswer: null,
        leftAt: null,
        rightAt: null,
        roundStartedAt: 0,
        matchTimerId: null,
        matchSecondsLeft: MATCH_DURATION_SECONDS,
        running: false,
        resolving: false,
        log: [],
        loadingBatch: null,
    };

    function saved() {
        try {
            return JSON.parse(localStorage.getItem(storageKey) || "{}");
        } catch {
            return {};
        }
    }

    function persist() {
        localStorage.setItem(
            storageKey,
            JSON.stringify({ grade: state.grade, leftName: state.leftName, rightName: state.rightName }),
        );
    }

    function normalize(value, fallback) {
        return ((value || "").trim().replace(/\s+/g, " ")) || fallback;
    }

    function meta(grade) {
        return gradeOptions.find((item) => item.value === grade) || null;
    }

    function formatSeconds(value) {
        const safe = Math.max(0, value);
        const minutes = String(Math.floor(safe / 60)).padStart(2, "0");
        const seconds = String(safe % 60).padStart(2, "0");
        return `${minutes}:${seconds}`;
    }

    function openOverlay() {
        els.overlay.classList.add("is-visible");
        document.body.style.overflow = "hidden";
    }
    function closeOverlay() {
        els.overlay.classList.remove("is-visible");
        document.body.style.overflow = "";
    }
    function setGrade(next) {
        state.grade = next;
        els.gradeCards.forEach((card) => card.classList.toggle("is-active", card.dataset.grade === next));
        const info = meta(next);
        state.gradeLabel = info ? info.label : "Tarix";
        [els.leftGrade, els.rightGrade, els.topbarGrade].forEach((node) => {
            node.textContent = state.gradeLabel;
        });
        els.topbarCount.textContent = "3 daqiqa";
    }

    function syncTeams() {
        els.teamOneName.textContent = state.leftName;
        els.teamTwoName.textContent = state.rightName;
        els.leftLabel.textContent = state.leftName;
        els.rightLabel.textContent = state.rightName;
        els.leftIconLabel.textContent = state.leftName;
        els.rightIconLabel.textContent = state.rightName;
        els.teamOneMeta.textContent = `${els.leftGrade.textContent} bo'yicha hujum qiladi.`;
        els.teamTwoMeta.textContent = `${els.rightGrade.textContent} bo'yicha qarshi turadi.`;
    }

    function clearTimers() {
        clearInterval(state.matchTimerId);
        state.matchTimerId = null;
    }

    function updateFrontline(tone = "") {
        const ratio = FRONTLINE_TARGET ? state.frontline / FRONTLINE_TARGET : 0;
        const shift = Math.max(-38, Math.min(38, ratio * 38));
        els.banner.style.left = `calc(50% + ${shift}%)`;
        els.banner.classList.remove("is-player-pulse", "is-bot-pulse");
        if (tone) {
            els.banner.classList.add(tone);
        }
    }

    function renderLog() {
        if (!state.log.length) {
            els.log.innerHTML = '<div class="battle-log-empty">O\'yin boshlangach so\'nggi natijalar shu yerga tushadi.</div>';
            return;
        }
        els.log.innerHTML = state.log
            .slice(0, 8)
            .map((item) => `<article class="battle-log-item ${item.tone}"><strong>${item.title}</strong><small>${item.text}</small></article>`)
            .join("");
    }

    function addLog(title, text, tone) {
        state.log.unshift({ title, text, tone });
        renderLog();
    }

    function currentPair() {
        return state.pairs[state.roundIndex] || null;
    }

    function pairQuestions(questions) {
        const pool = Array.isArray(questions) ? questions.slice() : [];
        const pairs = [];
        while (pool.length >= 2) {
            const left = pool.shift();
            let rightIndex = pool.findIndex((item) => item.text !== left.text);
            if (rightIndex < 0) {
                rightIndex = 0;
            }
            const [right] = pool.splice(rightIndex, 1);
            if (!right) break;
            pairs.push({ left, right });
        }
        return pairs;
    }

    function appendPairs(questions) {
        const freshPairs = pairQuestions(questions);
        state.pairs.push(...freshPairs);
        return freshPairs.length;
    }

    async function fetchBatch() {
        if (state.loadingBatch) {
            return state.loadingBatch;
        }
        state.loadingBatch = fetch(
            `${questionUrl}?grade=${encodeURIComponent(state.grade)}&limit=${QUESTION_BATCH_SIZE}`,
            { headers: { "X-Requested-With": "XMLHttpRequest" } },
        )
            .then(async (response) => {
                const payload = await response.json();
                if (!response.ok || !payload.ok) {
                    throw new Error(payload.message || "Savollarni yuklab bo'lmadi.");
                }
                state.gradeLabel = payload.grade_label || state.gradeLabel || "Tarix";
                [els.leftGrade, els.rightGrade, els.topbarGrade].forEach((node) => {
                    node.textContent = state.gradeLabel;
                });
                appendPairs(payload.questions || []);
                return payload;
            })
            .finally(() => {
                state.loadingBatch = null;
            });
        return state.loadingBatch;
    }

    async function ensureUpcomingPairs() {
        const remainingPairs = state.pairs.length - state.roundIndex;
        if (remainingPairs > LOW_WATERMARK_PAIRS) {
            return;
        }
        try {
            await fetchBatch();
        } catch (error) {
            if (state.running) {
                els.status.textContent = error.message || "Yangi savollarni yuklab bo'lmadi.";
            }
        }
    }

    function setScores() {
        const left = String(state.leftScore);
        const right = String(state.rightScore);
        els.scoreLeft.textContent = left;
        els.scoreRight.textContent = right;
        els.miniLeft.textContent = left;
        els.miniRight.textContent = right;
    }

    function resetBoard() {
        clearTimers();
        state.pairs = [];
        state.roundIndex = 0;
        state.leftScore = 0;
        state.rightScore = 0;
        state.frontline = 0;
        state.leftAnswer = null;
        state.rightAnswer = null;
        state.leftAt = null;
        state.rightAt = null;
        state.roundStartedAt = 0;
        state.running = false;
        state.resolving = false;
        state.log = [];
        state.matchSecondsLeft = MATCH_DURATION_SECONDS;
        setScores();
        els.progress.textContent = `0 round | finish ${FRONTLINE_TARGET}`;
        els.roundLabel.textContent = "Start kutilyapti";
        els.timer.textContent = formatSeconds(MATCH_DURATION_SECONDS);
        els.status.textContent = "Sinfni tanlang va o'yinni boshlang.";
        els.leftQuestion.textContent = "O'yin boshlangach ko'k jamoaga savol shu yerda chiqadi.";
        els.rightQuestion.textContent = "O'yin boshlangach qizil jamoaga savol shu yerda chiqadi.";
        els.leftSource.textContent = "Tarix";
        els.rightSource.textContent = "Tarix";
        els.leftOptions.innerHTML = "";
        els.rightOptions.innerHTML = "";
        updateFrontline();
        renderLog();
    }

    function paintOptions(container, q, side) {
        container.innerHTML = q.options.map((opt, idx) => `<button class="battle-option" type="button" data-side="${side}" data-index="${idx}"><strong>${String.fromCharCode(65 + idx)}. ${opt}</strong><small>${q.difficulty} daraja</small></button>`).join("");
        container.querySelectorAll(".battle-option").forEach((button) => {
            button.addEventListener("click", () => answer(side, Number(button.dataset.index)));
        });
    }
    function renderRound() {
        const pair = currentPair();
        if (!pair) {
            finish("Savollar tugadi, yakuniy natija chiqarildi.");
            return;
        }
        state.leftAnswer = null;
        state.rightAnswer = null;
        state.leftAt = null;
        state.rightAt = null;
        state.roundStartedAt = Date.now();
        state.resolving = false;
        els.roundLabel.textContent = `${state.roundIndex + 1}-round`;
        els.timer.textContent = formatSeconds(state.matchSecondsLeft);
        els.progress.textContent = `${state.roundIndex + 1} round | finish ${FRONTLINE_TARGET}`;
        els.status.textContent = "Har jamoa o'z savoliga javob beradi.";
        els.leftQuestion.textContent = pair.left.text;
        els.rightQuestion.textContent = pair.right.text;
        els.leftSource.textContent = pair.left.source_title;
        els.rightSource.textContent = pair.right.source_title;
        paintOptions(els.leftOptions, pair.left, "left");
        paintOptions(els.rightOptions, pair.right, "right");
        ensureUpcomingPairs();
    }

    function answer(side, index) {
        if (!state.running || state.resolving) return;
        if (side === "left" && state.leftAnswer !== null) return;
        if (side === "right" && state.rightAnswer !== null) return;
        if (side === "left") {
            state.leftAnswer = index;
            state.leftAt = Date.now();
            els.leftOptions.querySelector(`[data-index="${index}"]`)?.classList.add("is-selected");
        } else {
            state.rightAnswer = index;
            state.rightAt = Date.now();
            els.rightOptions.querySelector(`[data-index="${index}"]`)?.classList.add("is-selected");
        }
        if (state.leftAnswer !== null && state.rightAnswer !== null) {
            resolveRound(false);
        } else {
            els.status.textContent = side === "left"
                ? `${state.leftName} javob berdi, ${state.rightName} hali o'ynamoqda.`
                : `${state.rightName} javob berdi, ${state.leftName} hali o'ynamoqda.`;
        }
    }

    function mark(container, correct, selected) {
        container.querySelectorAll(".battle-option").forEach((button) => {
            const idx = Number(button.dataset.index);
            button.disabled = true;
            if (idx === correct) button.classList.add("is-correct");
            else if (idx === selected) button.classList.add("is-wrong");
        });
    }

    function getTimeoutWinnerText() {
        if (state.frontline > 0) return `${state.leftName} finishga yaqinroq bo'lgani uchun yutdi.`;
        if (state.frontline < 0) return `${state.rightName} finishga yaqinroq bo'lgani uchun yutdi.`;
        if (state.leftScore > state.rightScore) return `${state.leftName} ko'proq ochko yig'ib yutdi.`;
        if (state.rightScore > state.leftScore) return `${state.rightName} ko'proq ochko yig'ib yutdi.`;
        return "Vaqt tugadi va jang teng yakunlandi.";
    }

    function finish(reason = "") {
        if (!state.running && !state.resolving) return;
        clearTimers();
        state.running = false;
        state.resolving = false;
        els.roundLabel.textContent = "Yakun";
        els.timer.textContent = formatSeconds(state.matchSecondsLeft);
        let summary = reason || "Jang yakunlandi.";
        if (Math.abs(state.frontline) >= FRONTLINE_TARGET) {
            summary = state.frontline > 0
                ? `${state.leftName} finish chizig'iga yetib g'olib bo'ldi.`
                : `${state.rightName} finish chizig'iga yetib g'olib bo'ldi.`;
        } else if (state.matchSecondsLeft <= 0) {
            summary = getTimeoutWinnerText();
        } else if (!reason) {
            summary = getTimeoutWinnerText();
        }
        els.status.textContent = summary;
        els.leftQuestion.textContent = "Qayta o'ynash uchun shu tomondagi tugmadan foydalaning.";
        els.rightQuestion.textContent = "Yangi jamoa yoki sinf tanlash uchun o'ng tomondagi tugmadan foydalaning.";
        els.leftSource.textContent = "Yakun";
        els.rightSource.textContent = "Yakun";
        els.leftOptions.innerHTML = `<button class="battle-option" type="button" data-restart="1"><strong>Qayta o'ynash</strong><small>Shu jamoalar bilan 3 daqiqalik yangi duel</small></button>`;
        els.rightOptions.innerHTML = `<button class="battle-option" type="button" data-setup="1"><strong>Jamoalarni o'zgartirish</strong><small>Sinf va nomlarni qayta tanlash</small></button>`;
        els.leftOptions.querySelector("[data-restart='1']")?.addEventListener("click", startBattle);
        els.rightOptions.querySelector("[data-setup='1']")?.addEventListener("click", openOverlay);
        addLog(
            "Jang yakuni",
            `${summary} ${state.leftName}: ${state.leftScore} ochko, ${state.rightName}: ${state.rightScore} ochko.`,
            state.leftScore === state.rightScore && state.frontline === 0
                ? "is-draw"
                : state.frontline >= 0
                    ? "is-player"
                    : "is-bot",
        );
    }

    function resolveRound(fromTimeout) {
        if (!state.running || state.resolving) return;
        const pair = currentPair();
        if (!pair) return;
        state.resolving = true;
        const leftCorrect = state.leftAnswer === pair.left.correct_index;
        const rightCorrect = state.rightAnswer === pair.right.correct_index;
        mark(els.leftOptions, pair.left.correct_index, state.leftAnswer);
        mark(els.rightOptions, pair.right.correct_index, state.rightAnswer);
        if (leftCorrect) state.leftScore += POINTS_PER_CORRECT;
        if (rightCorrect) state.rightScore += POINTS_PER_CORRECT;
        let tone = "", title = "Teng round", text = "Bu round ikki tomonda ham teng tugadi.";
        if (leftCorrect && !rightCorrect) { state.frontline += 1; tone = "is-player-pulse"; title = `${state.leftName} oldinga chiqdi`; text = `${state.leftName} to'g'ri topdi, ${state.rightName} esa bu roundni boy berdi.`; }
        else if (!leftCorrect && rightCorrect) { state.frontline -= 1; tone = "is-bot-pulse"; title = `${state.rightName} oldinga chiqdi`; text = `${state.rightName} to'g'ri topdi, ${state.leftName} esa bu roundni boy berdi.`; }
        else if (leftCorrect && rightCorrect) {
            const l = state.leftAt || Date.now(), r = state.rightAt || Date.now();
            if (l < r) { state.frontline += 1; tone = "is-player-pulse"; title = `${state.leftName} tezroq ishladi`; text = "Ikkala jamoa ham to'g'ri topdi, lekin ko'k jamoa tezroq javob berdi."; }
            else if (r < l) { state.frontline -= 1; tone = "is-bot-pulse"; title = `${state.rightName} tezroq ishladi`; text = "Ikkala jamoa ham to'g'ri topdi, lekin qizil jamoa tezroq javob berdi."; }
            else { title = "Mutlaq tenglik"; text = "Ikkala jamoa ham bir xil tezlikda yakunladi."; }
        } else if (fromTimeout && state.leftAnswer === null && state.rightAnswer === null) { title = "Vaqt bilan yakun"; text = "So'nggi round yakuniga yetmay qoldi."; }
        else if (fromTimeout && state.leftAnswer !== null && state.rightAnswer === null) { title = `${state.leftName} ulgurdi`; text = `${state.rightName} vaqt tugashidan oldin javob bera olmadi.`; if (leftCorrect) { state.frontline += 1; tone = "is-player-pulse"; } }
        else if (fromTimeout && state.rightAnswer !== null && state.leftAnswer === null) { title = `${state.rightName} ulgurdi`; text = `${state.leftName} vaqt tugashidan oldin javob bera olmadi.`; if (rightCorrect) { state.frontline -= 1; tone = "is-bot-pulse"; } }
        setScores();
        els.status.textContent = text;
        updateFrontline(tone);
        addLog(title, `${text} (${pair.left.source_title} / ${pair.right.source_title})`, tone === "is-player-pulse" ? "is-player" : tone === "is-bot-pulse" ? "is-bot" : "is-draw");
        const reachedFinish = Math.abs(state.frontline) >= FRONTLINE_TARGET;
        const timeoutReached = state.matchSecondsLeft <= 0;
        setTimeout(() => {
            updateFrontline();
            state.roundIndex += 1;
            if (reachedFinish || timeoutReached) {
                finish(timeoutReached ? "Vaqt tugadi." : "");
                return;
            }
            state.resolving = false;
            renderRound();
        }, RESOLVE_DELAY_MS);
    }

    function startMatchTimer() {
        clearTimers();
        els.timer.textContent = formatSeconds(state.matchSecondsLeft);
        state.matchTimerId = setInterval(() => {
            if (!state.running) return;
            state.matchSecondsLeft = Math.max(0, state.matchSecondsLeft - 1);
            els.timer.textContent = formatSeconds(state.matchSecondsLeft);
            if (state.matchSecondsLeft <= 0) {
                clearTimers();
                if (!state.resolving) {
                    resolveRound(true);
                }
            }
        }, 1000);
    }

    async function startBattle() {
        state.leftName = normalize(els.teamOneInput.value, "1-jamoa");
        state.rightName = normalize(els.teamTwoInput.value, "2-jamoa");
        if (!state.grade) { els.status.textContent = "Avval sinfni tanlang."; openOverlay(); return; }
        persist(); syncTeams();
        els.startButton.disabled = true; els.startButton.textContent = "Yuklanmoqda...";
        try {
            resetBoard();
            const payload = await fetchBatch();
            if (!state.pairs.length) throw new Error("Bu sinf uchun duel boshlashga yetarli savol topilmadi.");
            state.running = true;
            state.matchSecondsLeft = MATCH_DURATION_SECONDS;
            [els.leftGrade, els.rightGrade, els.topbarGrade].forEach((node) => { node.textContent = payload.grade_label || state.gradeLabel || "Tarix"; });
            els.topbarCount.textContent = "3 daqiqa";
            setScores(); renderLog(); updateFrontline(); closeOverlay(); startMatchTimer(); renderRound();
        } catch (error) {
            els.status.textContent = error.message || "O'yinni boshlashda xatolik yuz berdi.";
            openOverlay();
        } finally {
            els.startButton.disabled = false;
            els.startButton.textContent = "O'yinni boshlash";
        }
    }

    const stored = saved();
    setGrade((stored.grade && meta(stored.grade) && stored.grade) || initialGrade || gradeOptions[0]?.value || "");
    state.leftName = normalize(stored.leftName, "1-jamoa");
    state.rightName = normalize(stored.rightName, "2-jamoa");
    els.teamOneInput.value = stored.leftName || "";
    els.teamTwoInput.value = stored.rightName || "";
    syncTeams();
    resetBoard();
    if (els.overlay.classList.contains("is-visible")) document.body.style.overflow = "hidden";

    els.gradeCards.forEach((card) => card.addEventListener("click", () => setGrade(card.dataset.grade)));
    els.startButton?.addEventListener("click", startBattle);
    els.configButton?.addEventListener("click", openOverlay);
})();
