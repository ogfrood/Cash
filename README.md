# Cash

Gestor financeiro pessoal, mobile-first. Salário semanal em hospitality (Brisbane), caixinhas com metas, contas com reserva automática, dívidas com progressão diária, e — em breve — sincronização automática de turnos (Tanda) e payslips (Xero) pelo email.

Preto e verde, feito para caber num polegar.

## Correr no teu computador

Precisas de **Node.js 20+** e **npm** (Node LTS traz o npm). Passos:

```bash
# 1. Clonar (branch do desenvolvimento)
git clone https://github.com/ogfrood/Cash.git
cd Cash
git checkout claude/financial-manager-buckets-nxx93m

# 2. Instalar
npm install

# 3. Criar a base de dados e semear com dados de exemplo
npm run db:migrate
npm run db:seed

# 4. Arrancar
npm run dev
```

Abre <http://localhost:3000> no browser.

## Ver no telemóvel (na mesma rede)

Enquanto o `npm run dev` está a correr no computador, descobre o IP local:

- **macOS**: `ipconfig getifaddr en0`
- **Linux**: `hostname -I | awk '{print $1}'`
- **Windows**: `ipconfig` (procura "IPv4")

No telemóvel, na **mesma rede Wi-Fi**, abre `http://SEU-IP:3000` (por exemplo `http://192.168.1.42:3000`). Instala à *home screen* pelo menu de partilha do Safari/Chrome — comporta-se como app.

Se não quiseres depender do Wi-Fi partilhado, o mais limpo é o [Tailscale](https://tailscale.com/download): grátis para uso pessoal, instala no computador e no telemóvel, e o telemóvel passa a ver o computador de qualquer sítio como se estivesse na mesma rede.

## Comandos

| | |
|---|---|
| `npm run dev` | Arranca o servidor de desenvolvimento |
| `npm run db:migrate` | Aplica migrações à `data/cash.db` |
| `npm run db:seed` | Recria a base de dados com dados de exemplo |
| `npm run test` | Corre os testes unitários (Vitest) |
| `npm run db:generate` | Gera nova migração após editar `src/db/schema.ts` |

Toda a data é local em `data/cash.db` (SQLite). Faz cópia deste ficheiro para teres backup.

## Estado atual

**Fase 1 (funcional)** — caixinhas, contas com reserva semanal, dívidas com pace diário, entradas avulsas (ABN/informal/gorjetas), painel com progressão salarial e barra de progresso até $45.000 (WHM).

**Próximas fases** — cálculo de líquido a partir dos turnos com penalty rates + WHM; ingest automático dos emails do Tanda e do Xero via IMAP; reconciliação previsto vs. real; possível tracker de crypto (portfolio + previsão simples com track-record visualizado, sem promessas).

Plano completo em `/root/.claude/plans/vamos-criar-um-app-fancy-lemon.md`.
