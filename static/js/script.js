document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('wizard-form');
    const steps = document.querySelectorAll('.step');
    const btnPrev = document.getElementById('btn-prev');
    const btnNext = document.getElementById('btn-next');
    const progressFill = document.getElementById('progress-fill');
    const stepIndicator = document.getElementById('step-indicator');
    const stepLabel = document.getElementById('step-label');

    let currentStep = 1;
    const totalSteps = steps.length;

    // ── Build step dots ──────────────────────────────────────────────
    for (let i = 1; i <= totalSteps; i++) {
        const dot = document.createElement('div');
        dot.className = 'step-dot' + (i === 1 ? ' active' : '');
        dot.dataset.stepDot = i;
        stepIndicator.appendChild(dot);
    }

    const updateDots = () => {
        document.querySelectorAll('.step-dot').forEach(dot => {
            const n = parseInt(dot.dataset.stepDot);
            dot.className = 'step-dot' +
                (n === currentStep ? ' active' : n < currentStep ? ' done' : '');
        });
    };

    // ── Navigation ───────────────────────────────────────────────────
    const updateWizard = () => {
        steps.forEach(step => {
            step.classList.toggle('active', parseInt(step.dataset.step) === currentStep);
        });

        btnPrev.disabled = currentStep === 1;
        btnNext.textContent = currentStep === totalSteps ? 'Confirmar e Enviar ✓' : 'Próximo →';

        const progress = (currentStep / totalSteps) * 100;
        progressFill.style.width = `${progress}%`;

        if (stepLabel) stepLabel.textContent = `Etapa ${currentStep} de ${totalSteps}`;

        updateDots();
        validateCurrentStep();
        if (currentStep === totalSteps) buildPreview();
    };

    const validateCurrentStep = () => {
        const activeStep = document.querySelector('.step.active');
        if (!activeStep) return;
        const inputs = activeStep.querySelectorAll('input[required], select[required], textarea[required]');
        let isValid = true;

        inputs.forEach(input => {
            if (input.type === 'file') {
                if (!input.files || input.files.length === 0) isValid = false;
            } else if (!input.value.trim()) {
                isValid = false;
            }
        });

        // Custom CNAE validation
        if (currentStep === 6) {
            const cnaeCod = document.getElementById('cnae_codigo').value;
            const cnaeManual = document.getElementById('cnae-definir').checked;
            const ramoDesc = document.querySelector('textarea[name="ramo_descricao"]').value;
            if (!cnaeCod && (!cnaeManual || !ramoDesc.trim())) isValid = false;
        }

        btnNext.disabled = !isValid;
    };

    btnNext.addEventListener('click', async () => {
        if (currentStep < totalSteps) {
            currentStep++;
            updateWizard();
        } else {
            await submitWizard();
        }
    });

    btnPrev.addEventListener('click', () => {
        if (currentStep > 1) {
            currentStep--;
            updateWizard();
        }
    });

    form.addEventListener('input', validateCurrentStep);
    form.addEventListener('change', validateCurrentStep);

    // ── ViaCEP ───────────────────────────────────────────────────────
    const cepInput = document.getElementById('cep');
    cepInput.addEventListener('blur', async () => {
        const cep = cepInput.value.replace(/\D/g, '');
        if (cep.length === 8) {
            try {
                const res = await fetch(`https://viacep.com.br/ws/${cep}/json/`);
                const data = await res.json();
                if (!data.erro) {
                    document.getElementById('rua').value = data.logradouro;
                    document.getElementById('bairro').value = data.bairro;
                    document.getElementById('cidade').value = data.localidade;
                    document.getElementById('uf').value = data.uf;
                    if (!data.logradouro) {
                        showToast('Este CEP é genérico. Use o CEP específico da rua.', 'error');
                        cepInput.value = '';
                    }
                } else {
                    showToast('CEP não encontrado.', 'error');
                }
            } catch (e) {
                console.error('Erro ao buscar CEP', e);
            }
        }
        validateCurrentStep();
    });

    // CEP mask
    cepInput.addEventListener('input', (e) => {
        let v = e.target.value.replace(/\D/g, '').slice(0, 8);
        if (v.length > 5) v = v.slice(0, 5) + '-' + v.slice(5);
        e.target.value = v;
    });

    // Fetch on Enter key
    cepInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            cepInput.dispatchEvent(new Event('blur'));
        }
    });

    // ── CNAE Autocomplete ─────────────────────────────────────────────
    const cnaeSearch = document.getElementById('cnae-search');
    const cnaeResults = document.getElementById('cnae-results');
    const cnaeDefinir = document.getElementById('cnae-definir');
    const ramoManual = document.getElementById('ramo-manual');

    let cnaeDebounceTimer = null;
    let cnaeAbortController = null;

    cnaeSearch.addEventListener('input', (e) => {
        const query = e.target.value.trim();
        cnaeResults.innerHTML = '';
        if (query.length < 2) return;

        if (cnaeAbortController) cnaeAbortController.abort();
        clearTimeout(cnaeDebounceTimer);

        cnaeDebounceTimer = setTimeout(async () => {
            cnaeAbortController = new AbortController();
            const { signal } = cnaeAbortController;
            try {
                const res = await fetch(`/api/cnae?q=${encodeURIComponent(query)}`, { signal });
                if (!res.ok || signal.aborted) return;
                const items = await res.json();

                cnaeResults.innerHTML = '';
                items.forEach(item => {
                    const div = document.createElement('div');
                    div.textContent = `${item.id} — ${item.descricao}`;
                    div.onclick = () => {
                        document.getElementById('cnae_codigo').value = item.id;
                        document.getElementById('cnae_descricao').value = item.descricao;
                        cnaeSearch.value = `${item.id} — ${item.descricao}`;
                        cnaeResults.innerHTML = '';
                        validateCurrentStep();
                    };
                    cnaeResults.appendChild(div);
                });
            } catch (err) {
                if (err.name !== 'AbortError') console.error('Erro ao buscar CNAE', err);
            }
        }, 250);
    });

    cnaeDefinir.addEventListener('change', (e) => {
        ramoManual.style.display = e.target.checked ? 'block' : 'none';
        if (e.target.checked) {
            cnaeSearch.value = '';
            document.getElementById('cnae_codigo').value = '';
        }
        validateCurrentStep();
    });

    // ── Capital Social ────────────────────────────────────────────────
    const tipoIntegralizacao = document.getElementById('tipo_integralizacao');
    const dataLimiteGrp = document.getElementById('data-limite-group');

    // BRL currency mask for Valor Capital
    const capitalDisplay = document.getElementById('valor_capital_display');
    const capitalRaw = document.getElementById('valor_capital_raw');

    if (capitalDisplay) {
        const formatBRL = (cents) => {
            // cents is an integer, e.g. 100000 = R$ 1.000,00
            const str = String(cents).padStart(3, '0');
            const reais = str.slice(0, -2).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
            const centavos = str.slice(-2);
            return `R$ ${reais},${centavos}`;
        };

        capitalDisplay.addEventListener('input', () => {
            // Strip everything except digits
            const digits = capitalDisplay.value.replace(/\D/g, '').replace(/^0+/, '') || '0';
            const cents = parseInt(digits, 10);
            capitalDisplay.value = formatBRL(cents);
            // Store raw value as decimal string for the backend
            capitalRaw.value = (cents / 100).toFixed(2);
            validateCurrentStep();
        });

        // On focus: keep cursor at end
        capitalDisplay.addEventListener('focus', () => {
            const len = capitalDisplay.value.length;
            capitalDisplay.setSelectionRange(len, len);
        });
    }

    tipoIntegralizacao.addEventListener('change', (e) => {
        const isPrazo = e.target.value === 'prazo';
        dataLimiteGrp.style.display = isPrazo ? 'block' : 'none';
        dataLimiteGrp.querySelector('input').required = isPrazo;
        validateCurrentStep();
    });

    // ── Phone mask ────────────────────────────────────────────────────
    const telInput = document.getElementById('telefone');
    telInput.addEventListener('input', (e) => {
        let x = e.target.value.replace(/\D/g, '').match(/(\d{0,2})(\d{0,5})(\d{0,4})/);
        e.target.value = !x[2] ? x[1] : '(' + x[1] + ') ' + x[2] + (x[3] ? '-' + x[3] : '');
    });

    // ── Inscrição Imobiliária mask (IPTU) — formato 0000.0000.000.0000 ──
    const inscricaoInput = document.getElementById('inscricao_imobiliaria');
    if (inscricaoInput) {
        inscricaoInput.addEventListener('input', (e) => {
            // Remove tudo que não for dígito e limita a 15 dígitos
            const digits = e.target.value.replace(/\D/g, '').slice(0, 15);
            let v = digits;
            // Aplica pontos: 4 . 4 . 3 . 4
            if (v.length > 4) v = v.slice(0, 4) + '.' + v.slice(4);
            if (v.length > 9) v = v.slice(0, 9) + '.' + v.slice(9);
            if (v.length > 13) v = v.slice(0, 13) + '.' + v.slice(13);
            e.target.value = v;
            validateCurrentStep();
        });
    }

    // ── Submit ────────────────────────────────────────────────────────
    const submitWizard = async () => {
        const formData = new FormData(form);
        btnNext.disabled = true;
        btnNext.textContent = 'Enviando…';

        try {
            const res = await fetch('/submit', { method: 'POST', body: formData });
            const result = await res.json();

            if (result.status === 'success') {
                document.getElementById('wizard-container').innerHTML = `
                    <div class="success-screen">
                        <div class="success-icon">✓</div>
                        <h2>Solicitação Enviada!</h2>
                        <p>Seus dados foram encaminhados para o setor societário da<br><strong>Mendonça Galvão Contadores Associados</strong>.</p>
                        <p>Em breve nossa equipe entrará em contato.</p>
                        <div class="success-id">ID: ${result.id}</div>
                        <br><br>
                        <button onclick="window.location.reload()" class="btn-next" style="margin:auto">Nova Solicitação</button>
                    </div>
                    <footer>
                        <span>Núcleo Digital</span> — Mendonça Galvão Contadores Associados. Todos os direitos reservados.
                    </footer>
                `;
            } else {
                throw new Error('Erro na submissão');
            }
        } catch (e) {
            showToast('Erro ao enviar formulário. Tente novamente.', 'error');
            btnNext.disabled = false;
            btnNext.textContent = 'Enviar ✓';
        }
    };

    // ── Toast Notification ────────────────────────────────────────────
    const showToast = (msg, type = 'info') => {
        let toast = document.createElement('div');
        toast.textContent = msg;
        Object.assign(toast.style, {
            position: 'fixed',
            bottom: '28px',
            left: '50%',
            transform: 'translateX(-50%) translateY(20px)',
            background: type === 'error' ? 'rgba(224,96,96,0.9)' : 'rgba(185,152,90,0.9)',
            color: '#fff',
            padding: '12px 24px',
            borderRadius: '10px',
            fontSize: '0.875rem',
            fontWeight: '500',
            backdropFilter: 'blur(8px)',
            boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
            zIndex: '9999',
            transition: 'all 0.35s ease',
            opacity: '0',
        });
        document.body.appendChild(toast);
        requestAnimationFrame(() => {
            toast.style.opacity = '1';
            toast.style.transform = 'translateX(-50%) translateY(0)';
        });
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(-50%) translateY(10px)';
            setTimeout(() => toast.remove(), 400);
        }, 3500);
    };

    // ── Preview Builder ───────────────────────────────────────────────

    // Rótulos legíveis para campos select
    const SELECT_LABELS = {
        tipo_imovel: {
            sala: 'Sala Comercial',
            galpao: 'Galpão',
            loja: 'Loja',
            casa: 'Casa Comercial',
        },
        tipo_integralizacao: {
            ato: 'Integralizado No Ato (À Vista)',
            prazo: 'A Integralizar (Em Prazo Futuro)',
        },
        meio_integralizacao: {
            dinheiro: 'Moeda Corrente (Dinheiro)',
            bens: 'Bens (Móveis / Imóveis)',
        },
    };

    const PREVIEW_SECTIONS = [
        {
            title: '📋 Razão Social',
            fields: [
                { label: 'Opção 1 — Preferencial', name: 'razao_social_1' },
                { label: 'Opção 2', name: 'razao_social_2' },
                { label: 'Opção 3', name: 'razao_social_3' },
                { label: 'Nome Fantasia', name: 'nome_fantasia' },
            ]
        },
        {
            title: '📍 Endereço',
            fields: [
                { label: 'CEP', name: 'cep' },
                { label: 'Rua', name: 'rua' },
                { label: 'Número', name: 'numero' },
                { label: 'Complemento', name: 'complemento' },
                { label: 'Bairro', name: 'bairro' },
                { label: 'Cidade / UF', name: ['cidade', 'uf'], join: ' — ' },
            ]
        },
        {
            title: '🏢 Imóvel',
            fields: [
                { label: 'Inscrição Imobiliária', name: 'inscricao_imobiliaria' },
                { label: 'Área (m²)', name: 'area_m2' },
                { label: 'Tipo de Imóvel', name: 'tipo_imovel', select: true },
            ]
        },
        {
            title: '🔍 Atividade Econômica (CNAE)',
            fields: [
                { label: 'Código CNAE', name: 'cnae_codigo' },
                { label: 'Descrição', name: 'cnae_descricao' },
                { label: 'Ramo (manual)', name: 'ramo_descricao' },
            ]
        },
        {
            title: '💰 Capital Social',
            fields: [
                { label: 'Valor (R$)', name: 'valor_capital', format: 'brl' },
                { label: 'Integralização', name: 'tipo_integralizacao', select: true },
                { label: 'Data Limite', name: 'data_limite' },
                { label: 'Meio', name: 'meio_integralizacao', select: true },
            ]
        },
        {
            title: '📬 Contato',
            fields: [
                { label: 'E-mail', name: 'email' },
                { label: 'Telefone', name: 'telefone' },
            ]
        },
    ];

    const getVal = (name) => {
        if (Array.isArray(name)) {
            return name.map(n => {
                const el = form.querySelector(`[name="${n}"]`);
                return el ? el.value.trim() : '';
            });
        }
        const el = form.querySelector(`[name="${name}"]`);
        return el ? el.value.trim() : '';
    };

    const formatBRLDisplay = (raw) => {
        const num = parseFloat(raw);
        if (isNaN(num)) return raw;
        return 'R$ ' + num.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    };

    const buildPreview = () => {
        const container = document.getElementById('preview-content');
        if (!container) return;
        container.innerHTML = '';

        PREVIEW_SECTIONS.forEach(section => {
            const rows = section.fields.map(f => {
                let val;
                if (Array.isArray(f.name)) {
                    const parts = getVal(f.name);
                    val = parts.filter(v => v).join(f.join || ' ');
                } else {
                    val = getVal(f.name);
                }
                if (!val) return '';

                // Aplicar formatações específicas
                if (f.select && SELECT_LABELS[f.name]) {
                    val = SELECT_LABELS[f.name][val] || val;
                }
                if (f.format === 'brl') {
                    val = formatBRLDisplay(val);
                }

                return `<div class="preview-row">
                    <span class="preview-label">${f.label}</span>
                    <span class="preview-value">${val}</span>
                </div>`;
            }).join('');

            if (!rows) return;

            const sec = document.createElement('div');
            sec.className = 'preview-section';
            sec.innerHTML = `<div class="preview-section-title">${section.title}</div>${rows}`;
            container.appendChild(sec);
        });

        // Documentos
        const fileFields = [
            { label: 'Identidade', name: 'doc_identidade' },
            { label: 'Residência', name: 'doc_residencia' },
            { label: 'Certidão', name: 'doc_certidao' },
        ];
        const fileRows = fileFields.map(f => {
            const el = form.querySelector(`[name="${f.name}"]`);
            const fn = el && el.files && el.files[0] ? el.files[0].name : null;
            if (!fn) return '';
            return `<div class="preview-row">
                <span class="preview-label">${f.label}</span>
                <span class="preview-value">📎 ${fn}</span>
            </div>`;
        }).join('');

        if (fileRows) {
            const sec = document.createElement('div');
            sec.className = 'preview-section';
            sec.innerHTML = `<div class="preview-section-title">📄 Documentos</div>${fileRows}`;
            container.appendChild(sec);
        }
    };

    // ── Init ──────────────────────────────────────────────────────────
    updateWizard();
});
