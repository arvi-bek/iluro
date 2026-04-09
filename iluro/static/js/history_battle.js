(function () {
    const board = document.querySelector(".battle-board");
    if (!board) {
        return;
    }

    const questionUrl = board.dataset.questionUrl;
    const initialGrade = board.dataset.selectedGrade || "";
    const gradeOptions = JSON.parse(
        document.getElementById("history-battle-grade-options")?.textContent || "[]"
    );

    const elements = {
        gradeButtons: Array.from(document.querySelectorAll(".battle-grade-pill")),
        startButton: document.querySelector(".battle-start-button"),
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
    };

    const state = {
        selectedGrade: initialGrade,
        deck: [],
        roundIndex: 0,
        playerScore: 0,
        botScore: 0,
        frontline: 0,
        running: false,
        timer: 18,
        timerId: null,
        botAnswerId: null,
        playerAnswer: null,
        botAnswer: null,
        playerAnsweredAt: null,
        botAnsweredAt: null,
        roundStartedAt: 0,
    };

    function getGradeMeta(value) {
        return gradeOptions.find((item) => item.value === value) || null;
    }

    function setActiveGrade(nextGrade) {
        state.selectedGrade = nextGrade;
        elements.gradeButtons.forEach((button) => {
            button.classList.toggle("is-active", button.dataset.grade === nextGrade);
        });
        const meta = getGradeMeta(nextGrade);
        elements.gradeBadge.textContent = meta ? meta.label : "Tarix";
    }

    function resetVisualState() {
        elements.options.innerHTML = "";
        elements.questionText.textContent = "Jang boshlangach savol shu yerda chiqadi.";
        elements.sourceBadge.textContent = "Tarix";
        elements.playerScore.textContent = `${state.playerScore} ochko`;
        elements.botScore.textContent = `${state.botScore} ochko`;
        elements.progress.textContent = `${Math.min(state.roundIndex, state.deck.length)} / ${state.deck.length || 8}`;
        updateFrontline();
    }

    function updateFrontline() {
        const shift = Math.max(-38, Math.min(38, state.frontline * 12));
        elements.banner.style.left = `calc(50% + ${shift}%)`;
    }

    function clearTimers() {
        window.clearInterval(state.timerId);
        window.clearTimeout(state.botAnswerId);
        state.timerId = null;
        state.botAnswerId = null;
    }

    function renderLog(items) {
        if (!items.length) {
            elements.log.innerHTML = '<div class="battle-log-empty">O\'yin boshlangach so\'nggi natijalar shu yerga tushadi.</div>';
            return;
        }
        elements.log.innerHTML = items
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

    const history = [];

    function addLog(title, text, tone) {
        history.unshift({ title, text, tone });
        renderLog(history.slice(0, 6));
    }

    function getBotAccuracy(grade) {
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

    function renderQuestion() {
        const question = getCurrentQuestion();
        if (!question) {
            return;
        }

        state.playerAnswer = null;
        state.botAnswer = null;
        state.playerAnsweredAt = null;
        state.botAnsweredAt = null;
        state.timer = 18;
        state.roundStartedAt = Date.now();

        elements.roundLabel.textContent = `${state.roundIndex + 1}-round`;
        elements.timer.textContent = String(state.timer);
        elements.progress.textContent = `${state.roundIndex + 1} / ${state.deck.length}`;
        elements.status.textContent = "Savolga javob bering.";
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
            button.addEventListener("click", () => onPlayerAnswer(Number(button.dataset.index)));
        });

        scheduleBotAnswer();
        startTimer();
    }

    function scheduleBotAnswer() {
        const question = getCurrentQuestion();
        const accuracy = getBotAccuracy(question.grade || state.selectedGrade);
        const delay = 1800 + Math.floor(Math.random() * 3600);
        state.botAnswerId = window.setTimeout(() => {
            if (!state.running || state.botAnswer !== null) {
                return;
            }
            const shouldBeCorrect = Math.random() < accuracy;
            if (shouldBeCorrect) {
                state.botAnswer = question.correct_index;
            } else {
                const wrongIndexes = question.options
                    .map((_, index) => index)
                    .filter((index) => index !== question.correct_index);
                state.botAnswer = wrongIndexes[Math.floor(Math.random() * wrongIndexes.length)];
            }
            state.botAnsweredAt = Date.now();
            maybeResolveRound();
        }, delay);
    }

    function startTimer() {
        clearInterval(state.timerId);
        state.timerId = window.setInterval(() => {
            state.timer -= 1;
            elements.timer.textContent = String(Math.max(0, state.timer));
            if (state.timer <= 0) {
                clearTimers();
                maybeResolveRound(true);
            }
        }, 1000);
    }

    function onPlayerAnswer(index) {
        if (!state.running || state.playerAnswer !== null) {
            return;
        }
        state.playerAnswer = index;
        state.playerAnsweredAt = Date.now();
        const selected = elements.options.querySelector(`[data-index="${index}"]`);
        selected?.classList.add("is-selected");
        elements.status.textContent = "Javob qabul qilindi, raqib ham javob bermoqda.";
        maybeResolveRound();
    }

    function maybeResolveRound(force = false) {
        if (!state.running) {
            return;
        }
        if (!force && (state.playerAnswer === null || state.botAnswer === null)) {
            return;
        }

        clearTimers();
        const question = getCurrentQuestion();
        const playerCorrect = state.playerAnswer === question.correct_index;
        const botCorrect = state.botAnswer === question.correct_index;

        elements.options.querySelectorAll(".battle-option").forEach((button) => {
            const index = Number(button.dataset.index);
            button.disabled = true;
            if (index === question.correct_index) {
                button.classList.add("is-correct");
            } else if (index === state.playerAnswer || index === state.botAnswer) {
                button.classList.add("is-wrong");
            }
        });

        let tone = "is-draw";
        let title = "Draw";
        let text = "Hech kim frontni surmadi.";

        if (playerCorrect) {
            state.playerScore += 10;
        }
        if (botCorrect) {
            state.botScore += 10;
        }

        if (playerCorrect && !botCorrect) {
            state.frontline += 1;
            tone = "is-player";
            title = "Siz oldinga o'tdingiz";
            text = "To'g'ri javob berdingiz, bot esa xato qildi.";
        } else if (!playerCorrect && botCorrect) {
            state.frontline -= 1;
            tone = "is-bot";
            title = "Bot oldinga o'tdi";
            text = "Bot to'g'ri topdi, siz bu roundni boy berdingiz.";
        } else if (playerCorrect && botCorrect) {
            const playerTime = state.playerAnsweredAt || state.roundStartedAt + 18000;
            const botTime = state.botAnsweredAt || state.roundStartedAt + 18000;
            if (playerTime < botTime) {
                state.frontline += 1;
                tone = "is-player";
                title = "Tezlik siz tomonda";
                text = "Ikkalangiz ham to'g'ri topdingiz, lekin siz tezroq javob berdingiz.";
            } else if (botTime < playerTime) {
                state.frontline -= 1;
                tone = "is-bot";
                title = "Bot tezroq bo'ldi";
                text = "Ikkalangiz ham to'g'ri topdingiz, bot tezroq javob berdi.";
            } else {
                title = "Bir xil natija";
                text = "Ikkalangiz ham to'g'ri topdingiz, bu round teng o'tdi.";
            }
        } else if (force && state.playerAnswer === null && state.botAnswer === null) {
            title = "Vaqt tugadi";
            text = "Hech kim javob bermadi.";
        } else if (force && state.playerAnswer === null) {
            tone = botCorrect ? "is-bot" : "is-draw";
            title = botCorrect ? "Bot ulgurdi" : "Vaqt tugadi";
            text = botCorrect ? "Siz ulgurmadiz, bot javob berdi." : "Ikkala tomonda ham javob yo'q.";
            if (botCorrect) {
                state.frontline -= 1;
            }
        } else if (force && state.botAnswer === null) {
            tone = playerCorrect ? "is-player" : "is-draw";
            title = playerCorrect ? "Siz ulgurib oldingiz" : "Vaqt tugadi";
            text = playerCorrect ? "Bot ulgurmay qoldi, siz frontni oldinga surdingiz." : "Javob xato, bot ham ulgurmay qoldi.";
            if (playerCorrect) {
                state.frontline += 1;
            }
        }

        elements.playerScore.textContent = `${state.playerScore} ochko`;
        elements.botScore.textContent = `${state.botScore} ochko`;
        elements.status.textContent = text;
        updateFrontline();
        addLog(title, `${text} (${question.source_title})`, tone);

        window.setTimeout(() => {
            state.roundIndex += 1;
            if (state.roundIndex >= state.deck.length) {
                finishBattle();
            } else {
                renderQuestion();
            }
        }, 1400);
    }

    function finishBattle() {
        state.running = false;
        const summary =
            state.frontline > 0
                ? "Jang siz foydangizga tugadi."
                : state.frontline < 0
                  ? "Bot bu safar ustun keldi."
                  : state.playerScore >= state.botScore
                    ? "Ochko bo'yicha siz yuqoridasiz."
                    : "Ochko bo'yicha bot yuqori chiqdi.";

        elements.roundLabel.textContent = "Yakun";
        elements.timer.textContent = "0";
        elements.status.textContent = summary;
        elements.questionText.textContent = "Jang tugadi. Xohlasangiz shu sinf yoki boshqa sinf bilan qayta boshlang.";
        elements.startButton.disabled = false;
        elements.startButton.textContent = "Qayta boshlash";
        elements.options.innerHTML = "";
        elements.sourceBadge.textContent = "Yakuniy natija";
        addLog(
            "Jang yakuni",
            `${summary} Siz: ${state.playerScore} ochko, bot: ${state.botScore} ochko.`,
            state.frontline >= 0 ? "is-player" : "is-bot"
        );
    }

    async function startBattle() {
        if (!state.selectedGrade) {
            elements.status.textContent = "Avval sinfni tanlang.";
            return;
        }

        elements.startButton.disabled = true;
        elements.startButton.textContent = "Yuklanmoqda...";
        elements.status.textContent = "Tarix savollaridan deck yig'ilmoqda...";

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
            state.playerScore = 0;
            state.botScore = 0;
            state.frontline = 0;
            state.running = true;
            history.length = 0;
            renderLog([]);
            elements.gradeBadge.textContent = payload.grade_label || "Tarix";
            elements.startButton.textContent = "Jang davom etmoqda";
            resetVisualState();
            renderQuestion();
        } catch (error) {
            elements.status.textContent = error.message || "O'yinni boshlashda xatolik yuz berdi.";
            elements.startButton.disabled = false;
            elements.startButton.textContent = "Jangni boshlash";
        }
    }

    elements.gradeButtons.forEach((button) => {
        button.addEventListener("click", () => setActiveGrade(button.dataset.grade));
    });
    elements.startButton?.addEventListener("click", startBattle);

    setActiveGrade(initialGrade || elements.gradeButtons[0]?.dataset.grade || "");
    renderLog([]);
    resetVisualState();
})();
