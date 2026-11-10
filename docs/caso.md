# Caso: Pergunte aos dados

Resumo do projeto em uma página: problema, escopo, critérios, resultados e aprendizados.

## 1. Problema

Quem não sabe SQL depende de outra pessoa para responder perguntas simples sobre uma base de dados, e a resposta nem sempre é conferível.

**Para quem:** pessoas que precisam consultar uma base tabular sem escrever consultas.
**Hipótese:** um modelo de linguagem consegue traduzir perguntas em português para SQL com qualidade suficiente, desde que a consulta fique visível, seja validada antes de executar e o agente recuse o que não puder responder.

## 2. Escopo do MVP

**Dentro:** uma tabela pública (série mensal de preços de combustíveis por município, ANP, 2022 a 2025), uma pergunta por vez, geração e validação de SQL, execução somente leitura, explicação em uma frase, conjunto de perguntas de teste.
**Fora:** múltiplas tabelas, memória da conversa, atualização automática dos dados, usuários e permissões.

## 3. Critérios de sucesso

1. Nenhuma consulta de escrita é executada (testado com pedidos para apagar dados).
2. Perguntas fora do escopo (previsões, por exemplo) são recusadas.
3. Nas perguntas de teste do tipo consulta, o resultado da consulta gerada é igual ao da consulta escrita à mão. Não fixei uma meta numérica antes dos testes; o resultado está aqui como foi medido.
4. Toda resposta mostra a consulta usada.

## 4. Como foi feito

Python, Streamlit, SQLite e a API da OpenAI (`gpt-5-mini`). O código foi escrito com ajuda do Claude. Eu defini o problema e a base, baixei os dados da ANP, testei o app com perguntas reais, rodei a avaliação e testei a mudança de prompt. Na segurança, usei duas camadas: um validador de SQL e um banco aberto só para leitura, para que nenhuma escrita aconteça mesmo se o modelo errar. Desenvolvido entre 6 e 10 de novembro de 2026.

## 5. Resultados

Avaliação de 6/11/2026, `gpt-5-mini`, uma execução por pergunta.

| Critério | Resultado |
|---|---|
| 1. Nenhuma escrita executada | Atendido: o pedido de apagar dados foi recusado (avaliação e teste manual) |
| 2. Recusa fora do escopo | Atendido: previsão e pedido de apagar dados recusados |
| 3. Resultado igual ao esperado | v1: 9 de 10 perguntas de consulta; v2: 10 de 10 |
| 4. Consulta sempre visível | Atendido nas respostas testadas |

**Pergunta que falhou (v1):** a 10. O modelo devolveu a linha mensal mais cara em vez de agregar o ano por município. Corrigida no v2 com uma regra de agregação. As perguntas de recusa passaram nas duas versões.

## 6. O que aprendi e o que mudaria

- O erro mais relevante foi de interpretação (linha mensal em vez de agregação anual), não de sintaxe SQL.
- O ajuste no prompt corrigiu a falha, mas foi feito com as mesmas perguntas do teste; falta validar com perguntas novas.
- Sem resolver: a explicação em texto pode interpretar mal uma coluna extra (exemplo: "333 postos" a partir de uma soma de postos por mês).
- O comparador marca como diferente uma média simples, que seria uma interpretação válida.

## 7. Próximos passos

Aba de painel, repetição das perguntas para medir a variação, mais tabelas.
