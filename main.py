def main():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERRO: configure TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID.")
        return

    sent_hashes, recent_titles = load_state()
    new_count = 0

    total_checked = 0
    skip_already_sent = 0
    skip_duplicate_title = 0
    skip_not_relevant = 0
    skip_not_recent = 0
    skip_negative_keyword = 0

    for source, url in FEEDS.items():
        feed = fetch_feed(url)
        if not feed.entries:
            print("AVISO: Feed '" + source + "' retornou vazio ou falhou")
            continue

        for entry in feed.entries[:10]:
            total_checked += 1
            h = item_hash(entry)
            if h in sent_hashes:
                skip_already_sent += 1
                continue

            title = entry.get("title", "")
            if is_duplicate_title(title, recent_titles):
                skip_duplicate_title += 1
                sent_hashes.add(h)
                save_state(sent_hashes, recent_titles)
                continue

            text_check = (title + " " + get_entry_body(entry)).lower()
            if any(nw in text_check for nw in NEGATIVE_KEYWORDS):
                skip_negative_keyword += 1
                sent_hashes.add(h)
                save_state(sent_hashes, recent_titles)
                continue

            if not is_relevant(entry):
                skip_not_relevant += 1
                sent_hashes.add(h)
                save_state(sent_hashes, recent_titles)
                continue

            if not is_recent_enough(entry):
                skip_not_recent += 1
                sent_hashes.add(h)
                save_state(sent_hashes, recent_titles)
                continue

            raw_body = get_entry_body(entry)
            is_english = source not in PORTUGUESE_SOURCES

            ai_result = None
            if needs_ai(source, raw_body):
                ai_result = summarize_with_ai(title, raw_body, translate=is_english)

            message = format_message(source, entry, ai_result)

            if send_telegram_message(message):
                sent_hashes.add(h)
                recent_titles.append(title)
                new_count += 1
                sentiment_log = ai_result.get("sentiment") if ai_result else "N/A"
                print("Enviado: " + title[:50] + " [" + sentiment_log + "]")
                save_state(sent_hashes, recent_titles)
                time.sleep(3)

    print("=== DIAGNOSTICO ===")
    print("Total verificado: " + str(total_checked))
    print("Ja enviado antes: " + str(skip_already_sent))
    print("Titulo duplicado: " + str(skip_duplicate_title))
    print("Palavra negativa: " + str(skip_negative_keyword))
    print("Nao relevante: " + str(skip_not_relevant))
    print("Nao e de hoje: " + str(skip_not_recent))
    print("Enviado com sucesso: " + str(new_count))
    print("Ciclo concluido. " + str(new_count) + " noticia(s) enviada(s).")
