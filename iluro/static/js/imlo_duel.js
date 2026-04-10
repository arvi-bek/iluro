(function () {
    const board = document.querySelector(".battle-board");
    if (!board) return;

    const storageKey = "iluro-imlo-duel-setup";
    const questionUrl = board.dataset.questionUrl;
    const initialSubject = board.dataset.selectedSubject || "language";
    const initialGrade = board.dataset.selectedGrade || "";
    const subjectOptions = JSON.parse(document.getElementById("language-duel-subject-options")?.textContent || "[]");
    const gradeOptionsMap = JSON.parse(document.getElementById("language-duel-grade-options")?.textContent || "{}");
    const gradeOptions = Array.isArray(gradeOptionsMap?.[initialSubject]) ? gradeOptionsMap[initialSubject] : [];
    const MATCH_DURATION_SECONDS = 180;
    const QUESTION_BATCH_SIZE = 30;
    const LOW_WATERMARK_QUESTIONS = 4;
    const FRONTLINE_TARGET = 5;
    const POINTS_PER_CORRECT = 1;
    const RESOLVE_DELAY_MS = 900;

    const $ = (id) => document.getElementById(id);
    const els = {
        overlay: $("battle-setup-overlay"),
        resultOverlay: $("battle-result-overlay"),
        resultTitle: $("battle-result-title"),
        resultSummary: $("battle-result-summary"),
        restartButton: $("battle-restart-btn"),
        resultConfigButton: $("battle-result-config-btn"),
        subjectCards: Array.from(document.querySelectorAll(".game-subject-card")),
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
        subject: initialSubject,
        subjectLabel: "Ona tili",
        grade: "",
        gradeLabel: "Aralash",
        leftQueue: [],
        rightQueue: [],
        leftCurrent: null,
        rightCurrent: null,
        leftAnswered: 0,
        rightAnswered: 0,
        leftScore: 0,
        rightScore: 0,
        frontline: 0,
        leftName: "1-jamoa",
        rightName: "2-jamoa",
        leftLocked: false,
        rightLocked: false,
        matchTimerId: null,
        matchSecondsLeft: MATCH_DURATION_SECONDS,
        running: false,
        finished: false,
        log: [],
        loadingBatch: null,
    };

    const setGradeTexts = () => {
        [els.leftGrade, els.rightGrade].filter(Boolean).forEach((node) => {
            node.textContent = state.gradeLabel;
        });
        if (els.topbarGrade) {
            els.topbarGrade.textContent = `${state.subjectLabel} • ${state.gradeLabel}`;
        }
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
            JSON.stringify({
                subject: state.subject,
                grade: state.grade,
                leftName: state.leftName,
                rightName: state.rightName,
            }),
        );
    }

    function normalize(value, fallback) {
        return ((value || "").trim().replace(/\s+/g, " ")) || fallback;
    }

    function meta(grade) {
        return gradeOptions.find((item) => item.value === grade) || null;
    }

    function subjectMeta(subject) {
        return subjectOptions.find((item) => item.value === subject) || null;
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
        if (!els.resultOverlay?.classList.contains("is-visible")) {
            document.body.style.overflow = "";
        }
    }
    function openResultOverlay() {
        els.resultOverlay?.classList.add("is-visible");
        document.body.style.overflow = "hidden";
    }
    function closeResultOverlay() {
        els.resultOverlay?.classList.remove("is-visible");
        if (!els.overlay.classList.contains("is-visible")) {
            document.body.style.overflow = "";
        }
    }
    function setGrade(next) {
        state.grade = next;
        els.gradeCards.forEach((card) => card.classList.toggle("is-active", card.dataset.grade === next));
        const info = meta(next);
        state.gradeLabel = info ? info.label : "Aralash";
        setGradeTexts();
        els.topbarCount.textContent = "3 daqiqa";
    }

    function syncTeams() {
        els.teamOneName.textContent = state.leftName;
        els.teamTwoName.textContent = state.rightName;
        els.leftLabel.textContent = state.leftName;
        els.rightLabel.textContent = state.rightName;
        els.leftIconLabel.textContent = state.leftName;
        els.rightIconLabel.textContent = state.rightName;
        els.teamOneMeta.textContent = `${state.subjectLabel} • ${state.gradeLabel} bo'yicha savollar bilan o'ynaydi.`;
        els.teamTwoMeta.textContent = `${state.subjectLabel} • ${state.gradeLabel} bo'yicha savollar bilan o'ynaydi.`;
    }

    function clearTimers() {
        clearInterval(state.matchTimerId);
        state.matchTimerId = null;
    }

    function updateFrontline(tone = "") {
        const ratio = FRONTLINE_TARGET ? state.frontline / FRONTLINE_TARGET : 0;
        const shift = Math.max(-76, Math.min(76, ratio * -76));
        els.banner.style.left = `calc(50% + ${shift}px)`;
        board.style.setProperty("--pull-shift", `${shift}px`);
        board.style.setProperty("--team-left-shift", `${Math.round(shift * 0.34)}px`);
        board.style.setProperty("--team-right-shift", `${Math.round(shift * 0.34)}px`);
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

    function distributeQuestions(questions) {
        (Array.isArray(questions) ? questions : []).forEach((question, index) => {
            if (index % 2 === 0) {
                state.leftQueue.push(question);
            } else {
                state.rightQueue.push(question);
            }
        });
    }

    async function fetchBatch() {
        if (state.loadingBatch) {
            return state.loadingBatch;
        }
        state.loadingBatch = fetch(
            `${questionUrl}?subject=${encodeURIComponent(state.subject)}&grade=${encodeURIComponent(state.grade)}&limit=${QUESTION_BATCH_SIZE}`,
            { headers: { "X-Requested-With": "XMLHttpRequest" } },
        )
            .then(async (response) => {
                const payload = await response.json();
                if (!response.ok || !payload.ok) {
                    throw new Error(payload.message || "Savollarni yuklab bo'lmadi.");
                }
                state.subjectLabel = payload.subject_label || state.subjectLabel || "Ona tili";
                state.gradeLabel = payload.grade_label || state.gradeLabel || "Aralash";
                setGradeTexts();
                distributeQuestions(payload.questions || []);
                return payload;
            })
            .finally(() => {
                state.loadingBatch = null;
            });
        return state.loadingBatch;
    }

    async function ensureUpcomingQuestions() {
        const leftNeeds = state.leftQueue.length + (state.leftCurrent ? 1 : 0);
        const rightNeeds = state.rightQueue.length + (state.rightCurrent ? 1 : 0);
        if (leftNeeds > LOW_WATERMARK_QUESTIONS && rightNeeds > LOW_WATERMARK_QUESTIONS) {
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

    function updateProgress() {
        const totalAnswered = state.leftAnswered + state.rightAnswered;
        els.progress.textContent = `${totalAnswered} savol | Finish: ${FRONTLINE_TARGET}`;
    }

    function resetBoard() {
        clearTimers();
        state.leftQueue = [];
        state.rightQueue = [];
        state.leftCurrent = null;
        state.rightCurrent = null;
        state.leftAnswered = 0;
        state.rightAnswered = 0;
        state.leftScore = 0;
        state.rightScore = 0;
        state.frontline = 0;
        state.leftLocked = false;
        state.rightLocked = false;
        state.running = false;
        state.finished = false;
        state.log = [];
        state.matchSecondsLeft = MATCH_DURATION_SECONDS;
        setScores();
        updateProgress();
        els.roundLabel.textContent = "Duel";
        els.timer.textContent = formatSeconds(MATCH_DURATION_SECONDS);
        els.status.textContent = "Fan va sinfni tanlang, keyin o'yinni boshlang.";
        els.leftQuestion.textContent = "O'yin boshlangach ko'k jamoaga savol shu yerda chiqadi.";
        els.rightQuestion.textContent = "O'yin boshlangach qizil jamoaga savol shu yerda chiqadi.";
        els.leftSource.textContent = state.subjectLabel;
        els.rightSource.textContent = state.subjectLabel;
        els.leftOptions.innerHTML = "";
        els.rightOptions.innerHTML = "";
        updateFrontline();
        renderLog();
        closeResultOverlay();
    }

    function paintOptions(container, q, side) {
        container.innerHTML = q.options.map((opt, idx) => `<button class="battle-option" type="button" data-side="${side}" data-index="${idx}"><strong>${String.fromCharCode(65 + idx)}. ${opt}</strong></button>`).join("");
        container.querySelectorAll(".battle-option").forEach((button) => {
            button.addEventListener("click", () => answer(side, Number(button.dataset.index)));
        });
    }

    function renderSide(side) {
        const current = side === "left" ? state.leftCurrent : state.rightCurrent;
        const questionNode = side === "left" ? els.leftQuestion : els.rightQuestion;
        const sourceNode = side === "left" ? els.leftSource : els.rightSource;
        const optionsNode = side === "left" ? els.leftOptions : els.rightOptions;

        if (!current) {
            questionNode.textContent = side === "left"
                ? "Ko'k jamoa uchun yangi savol yuklanmoqda."
                : "Qizil jamoa uchun yangi savol yuklanmoqda.";
            sourceNode.textContent = "Kutilmoqda";
            optionsNode.innerHTML = "";
            return;
        }

        questionNode.textContent = current.text;
        sourceNode.textContent = current.source_title;
        paintOptions(optionsNode, current, side);
    }

    function consumeNextQuestion(side) {
        if (side === "left") {
            state.leftCurrent = state.leftQueue.shift() || null;
        } else {
            state.rightCurrent = state.rightQueue.shift() || null;
        }
        renderSide(side);
        ensureUpcomingQuestions();
    }

    function answer(side, index) {
        if (!state.running || state.finished) return;
        resolveAnswer(side, index);
    }

    function mark(container, correct, selected) {
        container.querySelectorAll(".battle-option").forEach((button) => {
            const idx = Number(button.dataset.index);
            button.disabled = true;
            if (idx === correct) button.classList.add("is-correct");
            else if (idx === selected) button.classList.add("is-wrong");
        });
    }

    function getWinnerSummary() {
        if (Math.abs(state.frontline) >= FRONTLINE_TARGET) {
            return state.frontline > 0
                ? `${state.leftName} finish chizig'iga yetib g'olib bo'ldi.`
                : `${state.rightName} finish chizig'iga yetib g'olib bo'ldi.`;
        }
        if (state.frontline > 0) return `${state.leftName} arqonni o'z tomoniga ko'proq tortib yutdi.`;
        if (state.frontline < 0) return `${state.rightName} arqonni o'z tomoniga ko'proq tortib yutdi.`;
        if (state.leftScore > state.rightScore) return `${state.leftName} ko'proq ochko yig'ib yutdi.`;
        if (state.rightScore > state.leftScore) return `${state.rightName} ko'proq ochko yig'ib yutdi.`;
        return "O'yin teng yakunlandi.";
    }

    function finish(reason = "") {
        if (state.finished) return;
        clearTimers();
        state.finished = true;
        state.running = false;
        state.leftLocked = true;
        state.rightLocked = true;
        els.roundLabel.textContent = "Yakun";
        els.timer.textContent = formatSeconds(state.matchSecondsLeft);
        const summary = reason || getWinnerSummary();
        els.status.textContent = summary;
        els.resultTitle.textContent = Math.abs(state.frontline) >= FRONTLINE_TARGET ? "G'olib aniqlandi" : "Vaqt tugadi";
        els.resultSummary.textContent = `${summary} ${state.leftName}: ${state.leftScore} ochko, ${state.rightName}: ${state.rightScore} ochko.`;
        addLog(
            "O'yin yakuni",
            els.resultSummary.textContent,
            state.leftScore === state.rightScore && state.frontline === 0
                ? "is-draw"
                : state.frontline >= 0
                    ? "is-player"
                    : "is-bot",
        );
        openResultOverlay();
    }

    function resolveAnswer(side, selectedIndex) {
        if (!state.running || state.finished) return;
        const isLeft = side === "left";
        const current = isLeft ? state.leftCurrent : state.rightCurrent;
        if (!current) return;
        const lockedKey = isLeft ? "leftLocked" : "rightLocked";
        const countKey = isLeft ? "leftAnswered" : "rightAnswered";
        const scoreKey = isLeft ? "leftScore" : "rightScore";
        if (state[lockedKey]) return;
        state[lockedKey] = true;
        state[countKey] += 1;
        const isCorrect = selectedIndex === current.correct_index;
        mark(isLeft ? els.leftOptions : els.rightOptions, current.correct_index, selectedIndex);
        let tone = "", title = "", text = "";
        if (isCorrect) {
            state[scoreKey] += POINTS_PER_CORRECT;
            state.frontline += isLeft ? 1 : -1;
            tone = isLeft ? "is-player-pulse" : "is-bot-pulse";
            title = isLeft ? `${state.leftName} oldinga chiqdi` : `${state.rightName} oldinga chiqdi`;
            text = `${isLeft ? state.leftName : state.rightName} to'g'ri topdi va arqonni o'z tomonga tortdi.`;
        } else {
            state.frontline += isLeft ? -1 : 1;
            tone = isLeft ? "is-bot-pulse" : "is-player-pulse";
            title = isLeft ? `${state.rightName} foyda oldi` : `${state.leftName} foyda oldi`;
            text = `${isLeft ? state.leftName : state.rightName} xato topdi, arqon raqib tomonga ketdi.`;
        }
        setScores();
        updateProgress();
        els.status.textContent = text;
        updateFrontline(tone);
        addLog(title, `${text} (${current.source_title})`, tone === "is-player-pulse" ? "is-player" : "is-bot");
        if (Math.abs(state.frontline) >= FRONTLINE_TARGET) {
            finish();
            return;
        }
        setTimeout(() => {
            if (state.finished) return;
            updateFrontline();
            if (isLeft) {
                state.leftCurrent = null;
                state.leftLocked = false;
                consumeNextQuestion("left");
            } else {
                state.rightCurrent = null;
                state.rightLocked = false;
                consumeNextQuestion("right");
            }
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
                finish();
            }
        }, 1000);
    }

    async function startBattle() {
        state.leftName = normalize(els.teamOneInput.value, "1-jamoa");
        state.rightName = normalize(els.teamTwoInput.value, "2-jamoa");
        if (!state.grade) { els.status.textContent = "Avval fan va sinfni tanlang."; openOverlay(); return; }
        persist(); syncTeams();
        els.startButton.disabled = true; els.startButton.textContent = "Yuklanmoqda...";
        try {
            resetBoard();
            const payload = await fetchBatch();
            if (!state.leftQueue.length || !state.rightQueue.length) {
                throw new Error("Tanlangan fan va sinf bo'yicha duel boshlashga yetarli savol topilmadi.");
            }
            state.running = true;
            state.matchSecondsLeft = MATCH_DURATION_SECONDS;
            state.subjectLabel = payload.subject_label || state.subjectLabel || "Ona tili";
            state.gradeLabel = payload.grade_label || state.gradeLabel || "Aralash";
            setGradeTexts();
            els.topbarCount.textContent = "3 daqiqa";
            setScores();
            renderLog();
            updateFrontline();
            closeOverlay();
            consumeNextQuestion("left");
            consumeNextQuestion("right");
            updateProgress();
            els.status.textContent = `${state.subjectLabel} • ${state.gradeLabel} bo'yicha duel boshlandi.`;
            startMatchTimer();
        } catch (error) {
            els.status.textContent = error.message || "O'yinni boshlashda xatolik yuz berdi.";
            openOverlay();
        } finally {
            els.startButton.disabled = false;
            els.startButton.textContent = "O'yinni boshlash";
        }
    }

    const stored = saved();
    const activeSubjectOption = subjectMeta(initialSubject) || subjectMeta(stored.subject) || subjectOptions[0] || null;
    if (activeSubjectOption) {
        state.subject = activeSubjectOption.value;
        state.subjectLabel = activeSubjectOption.label;
    }

    state.leftName = normalize(stored.leftName, "1-jamoa");
    state.rightName = normalize(stored.rightName, "2-jamoa");
    els.teamOneInput.value = stored.leftName || "";
    els.teamTwoInput.value = stored.rightName || "";

    const initialGradeValue = (stored.grade && meta(stored.grade) && stored.grade) || initialGrade || gradeOptions[0]?.value || "";
    setGrade(initialGradeValue);
    syncTeams();
    resetBoard();
    if (els.overlay.classList.contains("is-visible")) document.body.style.overflow = "hidden";

    els.subjectCards.forEach((card) => {
        card.classList.toggle("is-active", card.dataset.subject === state.subject);
        card.addEventListener("click", () => {
            const nextSubject = card.dataset.subject || "language";
            if (nextSubject === state.subject) {
                return;
            }
            const params = new URLSearchParams(window.location.search);
            params.set("subject", nextSubject);
            params.delete("grade");
            window.location.search = params.toString();
        });
    });
    els.gradeCards.forEach((card) => card.addEventListener("click", () => setGrade(card.dataset.grade)));
    els.startButton?.addEventListener("click", startBattle);
    els.configButton?.addEventListener("click", openOverlay);
    els.restartButton?.addEventListener("click", startBattle);
    els.resultConfigButton?.addEventListener("click", () => {
        closeResultOverlay();
        openOverlay();
    });
})();
