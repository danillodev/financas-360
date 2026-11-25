# Finanças 360

Portal estático de notícias e educação financeira. Hospedagem: GitHub Pages. Automação: GitHub Actions. Custo: R$ 0.

## Publicar em 6 passos
1. Crie uma conta no GitHub e um repositório **público** chamado `financas-360`.
2. Envie todos os arquivos desta pasta (botão *Add file > Upload files*, incluindo a pasta `.github`).
3. Em **Settings > Pages**, em *Source*, escolha **GitHub Actions**.
4. Em **Settings > Actions > General > Workflow permissions**, marque **Read and write permissions**.
5. Em **Actions > Publicação diária Finanças 360 > Run workflow** para publicar o primeiro post e colocar o site no ar.
6. Seu site fica em `https://SEU-USUARIO.github.io/financas-360/`. Depois disso, publica sozinho todo dia às 08h (Brasília).

## Seus links de afiliados
Edite `config/affiliates.json` (pode editar direto no GitHub):
- Amazon: preencha `amazon_tag` (ex.: `meusite-20`) e os produtos usam busca com sua tag.
- Mercado Livre e Shopee: cole o link gerado no painel de afiliados no campo `url` de cada item.
- Itens sem link não aparecem. Para adicionar produto, copie uma linha e mude título, descrição, categorias e `url`.

## Personalização (`config/site.json`)
`email`, `redes` (links das suas redes), `formspree_id` (formulário de contato gratuito em formspree.io), `google_analytics_id`.

## Texto com IA (grátis)
Por padrão usa o GitHub Models com o token do próprio Actions (sem configurar nada, com limite diário de uso gratuito).
Alternativa: crie um *secret* `AI_API_KEY` (ex.: chave gratuita do Google AI Studio) e as variáveis `AI_ENDPOINT` (`https://generativelanguage.googleapis.com/v1beta/openai/chat/completions`) e `AI_MODEL` (`gemini-2.0-flash`).

## Como evita erro e duplicação
- Só publica notícia confirmada por 2+ fontes, ou de fonte oficial (Agência Brasil).
- Compara com posts já publicados e com URLs já usadas (`data/seen.json`).
- Sem notícia confirmada, publica um guia atemporal.
- Erros ficam em `logs/errors.log`; são 3 tentativas (5 min entre elas); se falhar, abre uma *issue* no repositório. Você pode rodar de novo em *Run workflow*.

## Domínio
Não precisa de domínio: usa `github.io`. Feeds em `config/feeds.json` podem ser trocados/adicionados.
