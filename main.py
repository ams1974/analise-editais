import click

from core.config import FONTES_DISPONIVEIS, PERFIS_DISPONIVEIS, PERFIS_DIR, HISTORICO_DIR


@click.group()
@click.version_option(version="0.2.0")
def cli():
    """Análise de Editais PNUD/UNESCO/OEI Brasil - scraping, persistência e análise com classificação de perfil."""


@cli.command()
@click.option("--periodo", "-p", default=3, type=int, help="Meses para análise (padrão: 3)")
@click.option("--perfil", "-f", default=None, type=click.Choice(PERFIS_DISPONIVEIS), help="Filtrar por perfil")
@click.option("--todos", "-t", is_flag=True, help="Analisar todos os editais (ignora período)")
@click.option("--force", is_flag=True, help="Forçar análise mesmo sem editais novos")
@click.option("--fonte", multiple=True, type=click.Choice(FONTES_DISPONIVEIS), help="Restringir a fonte(s) (padrão: todas)")
def daily(periodo, perfil, todos, force, fonte):
    """Execução diária completa: fetch → persist → analyze → report."""
    from core.scraper import executar_scraping
    from core.persistence import carregar_editais_todos
    from core.analyzer import analisar_editais
    from core.reporter import gerar_relatorio_completo
    from core.tor_pipeline import baixar_e_extrair_tors
    from core.tor_direct import baixar_e_extrair_tors_diretos

    click.echo("=" * 60)
    click.echo("🚀 EXECUÇÃO DIÁRIA - ANÁLISE DE EDITAIS PNUD/UNESCO/OEI")
    click.echo("=" * 60)

    editais_atuais, novidades = executar_scraping(fontes=list(fonte) or None)
    if not editais_atuais:
        click.echo("❌ Nenhum edital encontrado. Abortando.")
        return

    editais_pnud = [e for e in editais_atuais if e.get("fonte", "pnud") == "pnud"]
    editais_diretos = [e for e in editais_atuais if e.get("fonte") in ("unesco", "oei")]

    click.echo("\n📎 Baixando e extraindo ToRs pendentes...")
    n_tors = baixar_e_extrair_tors(editais_pnud)
    n_tors += baixar_e_extrair_tors_diretos(editais_diretos)
    click.echo(f"   {n_tors} ToR(s) novo(s) baixado(s) e extraído(s)")

    tem_novos = novidades and novidades.get("novos_count", 0) > 0
    tem_encerrados = novidades and novidades.get("encerrados_count", 0) > 0

    if not tem_novos and not force:
        if tem_encerrados:
            click.echo(f"\n🔒 {novidades['encerrados_count']} editais encerrados, mas nenhum novo.")
        click.echo(f"\n📋 {len(editais_atuais)} editais ativos — sem novidades. Análise ignorada.")
        click.echo("   Use --force para forçar a análise mesmo assim.")
        return

    if novidades:
        if tem_novos:
            click.echo(f"\n📢 {novidades['novos_count']} NOVOS EDITAIS!")
        if tem_encerrados:
            click.echo(f"🔒 {novidades['encerrados_count']} encerrados")
        click.echo(f"📋 {novidades['total_atuais']} ativos no total")

    click.echo("\n📊 ANALISANDO...")
    if todos:
        editais_raw = carregar_editais_todos()
    else:
        editais_raw = editais_atuais

    analise = analisar_editais(
        editais=editais_raw,
        periodo_meses=periodo,
        perfil_nome=perfil,
        todos=todos,
    )

    click.echo(f"   Total analisado: {analise['total_editais']}")
    click.echo(f"   Perfis encontrados: {dict(analise.get('contagem_perfis', {}))}")

    click.echo("\n📝 GERANDO RELATÓRIOS...")
    excel_path, pdf_path = gerar_relatorio_completo(analise, novidades)

    click.echo(f"\n✅ Execução diária concluída!")
    click.echo(f"   📊 Excel: {excel_path}")
    click.echo(f"   📄 PDF: {pdf_path}")
    click.echo(f"   🌐 Site: https://ams1974.github.io/analise-editais/")


@cli.command()
@click.option("--fonte", multiple=True, type=click.Choice(FONTES_DISPONIVEIS), help="Restringir a fonte(s) (padrão: todas)")
def fetch(fonte):
    """Buscar e persistir novos editais (sem análise)."""
    from core.scraper import executar_scraping

    click.echo("🔍 Buscando editais...")
    editais, novidades = executar_scraping(fontes=list(fonte) or None)

    if editais:
        click.echo(f"✅ {len(editais)} editais capturados e persistidos.")
        if novidades:
            click.echo(f"   🆕 {novidades['novos_count']} novos")
            click.echo(f"   🔒 {novidades['encerrados_count']} encerrados")
    else:
        click.echo("⚠️ Nenhum edital encontrado.")


@cli.command()
@click.option("--periodo", "-p", default=3, type=int, help="Meses para análise (padrão: 3)")
@click.option("--perfil", "-f", default=None, type=click.Choice(PERFIS_DISPONIVEIS), help="Filtrar por perfil")
@click.option("--todos", "-t", is_flag=True, help="Analisar todos os editais persistidos")
@click.option("--fonte", default=None, type=click.Choice(FONTES_DISPONIVEIS), help="Filtrar por fonte")
def analyze(periodo, perfil, todos, fonte):
    """Analisar editais persistidos com opções de período e perfil."""
    from core.persistence import carregar_editais_todos
    from core.analyzer import analisar_editais

    editais = carregar_editais_todos()
    descricao = "TODOS os" if todos else "os"
    click.echo(f"📦 Analisando {descricao} editais persistidos ({len(editais)} registros)")

    if not editais:
        click.echo("❌ Nenhum edital encontrado. Execute 'fetch' primeiro.")
        return

    analise = analisar_editais(
        editais=editais,
        periodo_meses=periodo,
        perfil_nome=perfil,
        todos=todos,
        fonte_nome=fonte,
    )

    click.echo(f"\n📊 RESULTADO DA ANÁLISE:")
    click.echo(f"   Total: {analise['total_editais']} editais")
    click.echo(f"   Filtro: {'todos' if todos else f'últimos {periodo} meses'}{' + perfil=' + perfil if perfil else ''}{' + fonte=' + fonte if fonte else ''}")

    click.echo(f"\n🌐 Fontes:")
    for fonte_item, qtd in analise.get("contagem_fontes", {}).items():
        click.echo(f"   {fonte_item}: {qtd}")

    click.echo(f"\n📋 Tipos:")
    for tipo, qtd in analise.get("contagem_tipos", {}).items():
        click.echo(f"   {tipo}: {qtd}")

    click.echo(f"\n🏷️ Perfis classificados:")
    for perfil, qtd in analise.get("contagem_perfis", {}).items():
        click.echo(f"   {perfil}: {qtd}")

    valores = analise.get("valores", {})
    if valores.get("quantidade_com_valor", 0) > 0:
        click.echo(f"\n💰 Valores:")
        click.echo(f"   Mín: R$ {valores['minimo']:,.2f}")
        click.echo(f"   Máx: R$ {valores['maximo']:,.2f}")
        click.echo(f"   Méd: R$ {valores['medio']:,.2f}")

    if analise.get("por_perfil"):
        click.echo(f"\n👤 Oportunidades por perfil:")
        for nome, dados in analise["por_perfil"].items():
            click.echo(f"   {nome}: {dados['quantidade']} editais compatíveis")

    # Salvar processados para uso posterior
    from core.persistence import salvar_processados
    salvar_processados(analise["editais"])


@cli.command()
@click.option("--periodo", "-p", default=3, type=int, help="Meses para análise (padrão: 3)")
@click.option("--perfil", "-f", default=None, type=click.Choice(PERFIS_DISPONIVEIS), help="Filtrar por perfil")
@click.option("--todos", "-t", is_flag=True, help="Incluir todos os editais")
@click.option("--fonte", default=None, type=click.Choice(FONTES_DISPONIVEIS), help="Filtrar por fonte")
def report(periodo, perfil, todos, fonte):
    """Gerar relatórios Excel e PDF a partir dos editais persistidos."""
    from core.persistence import carregar_editais_todos
    from core.analyzer import analisar_editais
    from core.reporter import gerar_relatorio_completo

    editais = carregar_editais_todos()

    if not editais:
        click.echo("❌ Nenhum edital encontrado. Execute 'fetch' primeiro.")
        return

    analise = analisar_editais(
        editais=editais,
        periodo_meses=periodo,
        perfil_nome=perfil,
        todos=todos,
        fonte_nome=fonte,
    )

    gerar_relatorio_completo(analise)


@cli.command()
def profiles():
    """Listar perfis disponíveis e seus detalhes."""
    from core.perfil import carregar_perfis

    perfis = carregar_perfis()

    if not perfis:
        click.echo("⚠️ Nenhum perfil encontrado em perfis/")
        click.echo("Crie arquivos JSON em perfis/ para definir perfis personalizados.")
        return

    click.echo(f"📋 {len(perfis)} perfis disponíveis:\n")
    for nome, perfil in perfis.items():
        click.echo(f"  🏷️ {nome}")
        click.echo(f"     Descrição: {perfil.get('descricao', 'N/D')}")
        click.echo(f"     Graduações: {', '.join(perfil.get('graduacoes', []))}")
        click.echo(f"     Ferramentas: {', '.join(perfil.get('ferramentas', []))}")
        click.echo(f"     Áreas: {', '.join(perfil.get('areas_interesse', []))}")
        click.echo(f"     Idiomas: {', '.join(perfil.get('idiomas', []))}")
        click.echo(f"     Valor mínimo: R$ {perfil.get('valor_minimo', 0):,.2f}")
        click.echo()


@cli.command()
def status():
    """Verificar status dos dados persistidos."""
    from collections import Counter

    from core.persistence import carregar_editais_todos, carregar_editais_processados, ultimo_snapshot

    todos = carregar_editais_todos()
    processados = carregar_editais_processados()
    snap = ultimo_snapshot()

    click.echo("📊 STATUS DOS DADOS:\n")
    click.echo(f"   Editais únicos persistidos: {len(todos)}")
    por_fonte = Counter(e.get("fonte", "pnud") for e in todos)
    for fonte_item, qtd in por_fonte.most_common():
        click.echo(f"      {fonte_item}: {qtd}")
    click.echo(f"   Editais processados (última análise): {len(processados)}")
    click.echo(f"   Último snapshot: {snap.name if snap else 'Nenhum'}")
    click.echo(f"   Histórico: {len(list(HISTORICO_DIR.glob('*/*/*.json')))} snapshots")
    click.echo(f"   Perfis: {len(list(PERFIS_DIR.glob('*.json')))} configurados")


@cli.command(name="backfill-oei")
def backfill_oei():
    """Percorre o sitemap inteiro da OEI (todo o histórico do Brasil) e mescla em editais_todos.

    Uso pontual/manual — não faz parte do pipeline diário (volume grande, ~1.100 páginas)."""
    from core.persistence import atualizar_editais_todos
    from core.sources import oei

    click.echo("🔍 Percorrendo sitemap da OEI (histórico completo do Brasil)...")
    editais = oei.buscar_backfill()

    if not editais:
        click.echo("⚠️ Nenhum edital encontrado.")
        return

    novos, atualizados = atualizar_editais_todos(editais)
    click.echo(f"✅ {len(editais)} editais processados — {novos} novos, {atualizados} atualizados.")


if __name__ == "__main__":
    cli()
