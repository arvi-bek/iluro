(function () {
    const board = document.querySelector(".battle-board");
    if (!board) {
        return;
    }

    const storageKey = "iluro-history-battle-setup";
    const questionUrl = board.dataset.questionUrl;
    const initialGrade = board.dataset.selectedGrade || "";
    const gradeOptions = JSON.parse(
        document.getElementById("history-battle-grade-options")?.textContent || "[]"
    );

    const elements = {
        overlay: document.getElementById("battle-setup-overlay"),
        gradeCards: Array.from(document.querySelectorAll(".game-grade-card")),
        teamOneInput: document.getElementById("battle-team-one-input"),
        teamTwoInput: document.getElementById("battle-team-two-input"),
        startButton: document.getElementById("battle-start-btn"),
        configureButton: document.getElementById("battle-configure-btn"),
        banner: document.getElementById("battle-banner"),
        status: document.getElementById("battle-status"),
        progress: document.getElementById("battle-progress"),
        roundLabel: document.getElementById("battle-round-label"),
        timer: document.getElementById("battle-timer"),
        playerScore: document.getElementById("battle-player-score"),
        botScore: document.getElementById("battle-bot-score"),
        questionText: document.getElementById("battle-question-text"),
        options: document.getElementById("battle-options"),
        gradeBadge: document.getElementById("battle-grade-badge"),
        sourceBadge: document.getElementById("battle-source-badge"),
        log: document.getElementById("battle-log"),
        topbarGrade: document.getElementById("battle-topbar-grade"),
        topbarCount: document.getElementById("battle-topbar-count"),
        teamOneName: document.getElementById("battle-team-one-name"),
        teamTwoName: document.getElementById("battle-team-two-name"),
        teamOneMeta: document.getElementById("battle-team-one-meta"),
        teamTwoMeta: document.getElementById("battle-team-two-meta"),
        leftLabel: document.getElementById("battle-left-label"),
        rightLabel: document.getElementById("battle-right-label"),
    };

    const state = {
        selectedGrade: "",
        deck: [],
        roundIndex: 0,
        teamOneScore: 0,
        teamTwoScore: 0,
        frontline: 0,
        running: false,
        timer: 18,
        timerId: null,
        opponentAnswerId: null,
        teamOneAnswer: null,
        teamTwoAnswer: null,
        teamOneAnsweredAt: null,
        teamTwoAnsweredAt: null,
        roundStartedAt: 0,
        teamOneName: "1-jamoa",
        teamTwoName: "2-jamoa",
        log: [],
    };

    function getSavedSetup() {
        try {
            return JSON.parse(window.localStorage.getItem(storageKey) || "{}");
        } catch (error) {
            return {};
        }
    }

    function saveSetup() {
        window.localStorage.setItem(
            storageKey,
            JSON.stringify({
                grade: state.selectedGrade,
                teamOneName: state.teamOneName,
                teamTwoName: state.teamTwoName,
            })
        );
    }

    function getGradeMeta(value) {
        return gradeOptions.find((item) => item.value === value) || null;
    }

    function setActiveGrade(nextGrade) {
        state.selectedGrade = nextGrade;
        elements.gradeCards.forEach((card) => {
            card.classList.toggle("is-active", card.dataset.grade === nextGrade);
        });
        const meta = getGradeMeta(nextGrade);
        const gradeLabel = meta ? meta.label : "Tarix";
        elements.gradeBadge.textContent = gradeLabel;
        elements.topbarGrade.textContent = gradeLabel;
        if (meta) {
            elements.topbarCount.textContent = `${meta.question_count} savol`;
        }
    }

    function normalizeTeamName(value, fallback) {
        const cleaned = (value || "").trim().replace(/\s+/g, " ");
        return cleaned || fallback;
    }

    function syncTeamLabels() {
        elements.teamOneName.textContent = state.teamOneName;
        elements.teamTwoName.textContent = state.teamTwoName;
        elements.leftLabel.textContent = state.teamOneName;
        elements.rightLabel.textContent = state.teamTwoName;
        elements.teamOneMeta.textContent = `${elements.gradeBadge.textContent} bo'yicha hujum qilmoqda.`;
        elements.teamTwoMeta.textContent = `${elements.gradeBadge.textContent} bo'yicha raqib jamoa.`;
    }

    function openOverlay() {
        elements.overlay.classList.add("is-visible");
        document.body.style.overflow = "hidden";
    }

    function closeOverlay() {
        elements.overlay.classList.remove("is-visible");
        document.body.style.overflow = "";
    }

    function clearTimers() {
        window.clearInterval(state.timerId);
        window.clearTimeout(state.opponentAnswerId);
        state.timerId = null;
        state.opponentAnswerId = null;
    }

    function updateBannerTone(tone) {
        elements.banner.classList.remove("is-player-pulse", "is-bot-pulse");
        if (tone) {
            elements.banner.classList.add(tone);
        }
    }

    function updateFrontline() {
        const shift = Math.max(-38, Math.min(38, state.frontline * 12));
        elements.banner.style.left = `calc(50% + ${shift}%)`;
    }

    function renderLog() {
        if (!state.log.length) {
            elements.log.innerHTML = '<div class="battle-log-empty">O\'yin boshlangach so\'nggi natijalar shu yerga tushadi.</div>';
            return;
        }
        elements.log.innerHTML = state.log
            .slice(0, 6)
            .map(
                (item) => `
                    <article class="battle-log-item ${item.tone}">
                        <strong>${item.title}</strong>
                        <small>${item.text}</small>
                    </article>
                `
            )
            .join("");
    }

    function addLog(title, text, tone) {
        state.log.unshift({ title, text, tone });
        renderLog();
    }

    function getOpponentAccuracy(grade) {
        const map = {
            "5": 0.42,
            "6": 0.46,
            "7": 0.52,
            "8": 0.56,
            "9": 0.6,
            "10": 0.64,
            "11": 0.68,
        };
        return map[grade] || 0.55;
    }

    function getCurrentQuestion() {
        return state.deck[state.roundIndex] || null;
    }

    function resetScoreboard() {
        state.teamOneScore = 0;
        state.teamTwoScore = 0;
        state.frontline = 0;
        state.roundIndex = 0;
        state.running = false;
        state.log = [];
        elements.playerScore.textContent = "0 ochko";
        elements.botScore.textContent = "0 ochko";
        elements.progress.textContent = `0 / ${state.deck.length || 8}`;
        elements.roundLabel.textContent = "Boshlanish arafasi";
        elements.timer.textContent = "18";
        elements.status.textContent = "Sinfni tanlang va o'yinni boshlang.";
        elements.questionText.textContent = "O'yin boshlangach savol shu yerda chiqadi.";
        elements.sourceBadge.textContent = "Tarix";
        elements.options.innerHTML = "";
        updateFrontline();
        updateBannerTone("");
        renderLog();
    }

    function hydrateSetup() {
        const saved = getSavedSetup();
        const preferredGrade =
            (saved.grade && getGradeMeta(saved.grade) && saved.grade) ||
            initialGrade ||
            gradeOptions[0]?.value ||
            "";
        setActiveGrade(preferredGrade);

        state.teamOneName = normalizeTeamName(saved.teamOneName, "1-jamoa");
        state.teamTwoName = normalizeTeamName(saved.teamTwoName, "2-jamoa");
        elements.teamOneInput.value = saved.teamOneName || "";
        elements.teamTwoInput.value = saved.teamTwoName || "";
        syncTeamLabels();
        resetScoreboard();
        if (elements.overlay.classList.contains("is-visible")) {
            document.body.style.overflow = "hidden";
        }
    }

    function startTimer() {
        window.clearInterval(state.timerId);
        state.timerId = window.setInterval(() => {
            state.timer -= 1;
            elements.timer.textContent = String(Math.max(0, state.timer));
            if (state.timer <= 0) {
                clearTimers();
                maybeResolveRound(true);
            }
        }, 1000);
    }

    function scheduleOpponentAnswer() {
        const question = getCurrentQuestion();
        const accuracy = getOpponentAccuracy(question.grade || state.selectedGrade);
        const delay = 1800 + Math.floor(Math.random() * 3600);
        state.opponentAnswerId = window.setTimeout(() => {
            if (!state.running || state.teamTwoAnswer !== null) {
                return;
            }
            const shouldBeCorrect = Math.random() < accuracy;
            if (shouldBeCorrect) {
                state.teamTwoAnswer = question.correct_index;
            } else {
                const wrongIndexes = question.options
                    .map((_, index) => index)
                    .filter((index) => index !== question.correct_index);
                state.teamTwoAnswer = wrongIndexes[Math.floor(Math.random() * wrongIndexes.length)];
            }
            state.teamTwoAnsweredAt = Date.now();
            maybeResolveRound();
        }, delay);
    }

    function renderQuestion() {
        const question = getCurrentQuestion();
        if (!question) {
            return;
        }

        state.teamOneAnswer = null;
        state.teamTwoAnswer = null;
        state.teamOneAnsweredAt = null;
        state.teamTwoAnsweredAt = null;
        state.timer = 18;
        state.roundStartedAt = Date.now();

        elements.roundLabel.textContent = `${state.roundIndex + 1}-round`;
        elements.timer.textContent = String(state.timer);
        elements.progress.textContent = `${state.roundIndex + 1} / ${state.deck.length}`;
        elements.status.textContent = `${state.teamOneName}, javobni tanlang.`;
        elements.questionText.textContent = question.text;
        elements.sourceBadge.textContent = question.source_title;
        elements.options.innerHTML = question.options
            .map(
                (option, index) => `
                    <button class="battle-option" type="button" data-index="${index}">
                        <strong>${String.fromCharCode(65 + index)}. ${option}</strong>
                        <small>${question.difficulty} daraja</small>
                    </button>
                `
            )
            .join("");

        elements.options.querySelectorAll(".battle-option").forEach((button) => {
            button.addEventListener("click", () => onTeamOneAnswer(Number(button.dataset.index)));
        });

        scheduleOpponentAnswer();
        startTimer();
    }

    function onTeamOneAnswer(index) {
        if (!state.running || state.teamOneAnswer !== null) {
            return;
        }

        state.teamOneAnswer = index;
        state.teamOneAnsweredAt = Date.now();
        elements.options
            .querySelector(`[data-index="${index}"]`)
            ?.classList.add("is-selected");
        elements.status.textContent = `${state.teamOneName} javobni berdi, ${state.teamTwoName} kutilyapti.`;
        maybeResolveRound();
    }

    function maybeResolveRound(force = false) {
        if (!state.running) {
            return;
        }
        if (!force && (state.teamOneAnswer === null || state.teamTwoAnswer === null)) {
            return;
        }

        clearTimers();
        const question = getCurrentQuestion();
        const teamOneCorrect = state.teamOneAnswer === question.correct_index;
        const teamTwoCorrect = state.teamTwoAnswer === question.correct_index;

        elements.options.querySelectorAll(".battle-option").forEach((button) => {
            const index = Number(button.dataset.index);
            button.disabled = true;
            if (index === question.correct_index) {
                button.classList.add("is-correct");
            } else if (index === state.teamOneAnswer || index === state.teamTwoAnswer) {
                button.classList.add("is-wrong");
            }
        });

        if (teamOneCorrect) {
            state.teamOneScore += 10;
        }
        if (teamTwoCorrect) {
            state.teamTwoScore += 10;
        }

        let tone = "";
        let title = "Teng round";
        let text = "Bu roundda hech kim ustun kelmadi.";

        if (teamOneCorrect && !teamTwoCorrect) {
            state.frontline += 1;
            tone = "is-player-pulse";
            title = `${state.teamOneName} oldinga chiqdi`;
            text = `${state.teamOneName} to'g'ri javob berdi, ${state.teamTwoName} esa xato qildi.`;
        } else if (!teamOneCorrect && teamTwoCorrect) {
            state.frontline -= 1;
            tone = "is-bot-pulse";
            title = `${state.teamTwoName} oldinga chiqdi`;
            text = `${state.teamTwoName} to'g'ri javob berdi, ${state.teamOneName} esa xato qildi.`;
        } else if (teamOneCorrect && teamTwoCorrect) {
            const teamOneTime = state.teamOneAnsweredAt || state.roundStartedAt + 18000;
            const teamTwoTime = state.teamTwoAnsweredAt || state.roundStartedAt + 18000;
            if (teamOneTime < teamTwoTime) {
                state.frontline += 1;
                tone = "is-player-pulse";
                title = `${state.teamOneName} tezroq bo'ldi`;
                text = "Ikkala jamoa ham to'g'ri topdi, lekin ko'k jamoa tezroq javob berdi.";
            } else if (teamTwoTime < teamOneTime) {
                state.frontline -= 1;
                tone = "is-bot-pulse";
                title = `${state.teamTwoName} tezroq bo'ldi`;
                text = "Ikkala jamoa ham to'g'ri topdi, lekin qizil jamoa tezroq javob berdi.";
            } else {
                title = "Bir xil natija";
                text = "Ikkala jamoa ham bir vaqtda to'g'ri topdi.";
            }
        } else if (force && state.teamOneAnswer === null && state.teamTwoAnswer === null) {
            title = "Vaqt tugadi";
            text = "Bu roundda ikkala jamoa ham ulgurmay qoldi.";
        } else if (force && state.teamOneAnswer === null) {
            title = `${state.teamTwoName} ulgurdi`;
            text = `${state.teamOneName} ulgurmay qoldi.`;
            if (teamTwoCorrect) {
                state.frontline -= 1;
                tone = "is-bot-pulse";
            }
        } else if (force && state.teamTwoAnswer === null) {
            title = `${state.teamOneName} ulgurdi`;
            text = `${state.teamTwoName} ulgurmay qoldi.`;
            if (teamOneCorrect) {
                state.frontline += 1;
                tone = "is-player-pulse";
            }
        }

        elements.playerScore.textContent = `${state.teamOneScore} ochko`;
        elements.botScore.textContent = `${state.teamTwoScore} ochko`;
        elements.status.textContent = text;
        updateFrontline();
        updateBannerTone(tone);
        addLog(title, `${text} (${question.source_title})`, tone === "is-bot-pulse" ? "is-bot" : tone === "is-player-pulse" ? "is-player" : "is-draw");

        window.setTimeout(() => {
            updateBannerTone("");
            state.roundIndex += 1;
            if (state.roundIndex >= state.deck.length) {
                finishBattle();
            } else {
                renderQuestion();
            }
        }, 1500);
    }

    function finishBattle() {
        state.running = false;
        elements.roundLabel.textContent = "Yakun";
        elements.timer.textContent = "0";

        let summary = "Jang teng yakunlandi.";
        if (state.frontline > 0 || state.teamOneScore > state.teamTwoScore) {
            summary = `${state.teamOneName} g'olib bo'ldi.`;
        } else if (state.frontline < 0 || state.teamTwoScore > state.teamOneScore) {
            summary = `${state.teamTwoName} g'olib bo'ldi.`;
        }

        elements.status.textContent = summary;
        elements.questionText.textContent = "Yakun bo'ldi. Xohlasangiz sinfni yoki jamoa nomlarini almashtirib qayta boshlang.";
        elements.sourceBadge.textContent = "Yakuniy natija";
        elements.options.innerHTML = `
            <button class="battle-option" type="button" data-restart="true">
                <strong>Qayta o'ynash</strong>
                <small>Shu setup bilan battle'ni qayta boshlash</small>
            </button>
            <button class="battle-option" type="button" data-setup="true">
                <strong>Jamoalarni o'zgartirish</strong>
                <small>Sinf yoki nomlarni qayta tanlash</small>
            </button>
        `;
        elements.options.querySelector("[data-restart='true']")?.addEventListener("click", startBattle);
        elements.options.querySelector("[data-setup='true']")?.addEventListener("click", openOverlay);
        addLog(
            "Jang yakuni",
            `${summary} ${state.teamOneName}: ${state.teamOneScore} ochko, ${state.teamTwoName}: ${state.teamTwoScore} ochko.`,
            state.teamOneScore >= state.teamTwoScore ? "is-player" : "is-bot"
        );
    }

    async function startBattle() {
        state.teamOneName = normalizeTeamName(elements.teamOneInput.value, "1-jamoa");
        state.teamTwoName = normalizeTeamName(elements.teamTwoInput.value, "2-jamoa");

        if (!state.selectedGrade) {
            elements.status.textContent = "Avval sinfni tanlang.";
            openOverlay();
            return;
        }

        saveSetup();
        syncTeamLabels();
        elements.startButton.disabled = true;
        elements.startButton.textContent = "Yuklanmoqda...";
        elements.status.textContent = "Tarix savollaridan yangi deck yig'ilmoqda...";

        try {
            const response = await fetch(`${questionUrl}?grade=${encodeURIComponent(state.selectedGrade)}`, {
                headers: { "X-Requested-With": "XMLHttpRequest" },
            });
            const payload = await response.json();
            if (!response.ok || !payload.ok) {
                throw new Error(payload.message || "Savollarni yuklab bo'lmadi.");
            }

            state.deck = payload.questions || [];
            state.roundIndex = 0;
            state.teamOneScore = 0;
            state.teamTwoScore = 0;
            state.frontline = 0;
            state.running = true;
            state.log = [];
            elements.gradeBadge.textContent = payload.grade_label || "Tarix";
            elements.topbarGrade.textContent = payload.grade_label || "Tarix";
            elements.topbarCount.textContent = `${payload.question_count || state.deck.length} savol`;
            syncTeamLabels();
            closeOverlay();
            elements.startButton.disabled = false;
            elements.startButton.textContent = "O'yinni boshlash";
            renderLog();
            updateFrontline();
            renderQuestion();
        } catch (error) {
            elements.status.textContent = error.message || "O'yinni boshlashda xatolik yuz berdi.";
            elements.startButton.disabled = false;
            elements.startButton.textContent = "O'yinni boshlash";
            openOverlay();
        }
    }

    elements.gradeCards.forEach((card) => {
        card.addEventListener("click", () => setActiveGrade(card.dataset.grade));
    });

    elements.startButton?.addEventListener("click", startBattle);
    elements.configureButton?.addEventListener("click", openOverlay);

    hydrateSetup();
})();
