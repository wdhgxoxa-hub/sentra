"""
Módulo de Normalización, Limpieza Canónica e Interfoliado Temporal
==================================================================
Integra:
1. Saneamiento de marcas de borrado ([deleted], [removed]) y normalización de IDs (reddit-find).
2. Deduplicación canónica por ID y enlace estable (reddit-find / pain-miner).
3. Formateo de resultados crudos en Markdown estructurado de alta densidad para LLMs (reddit-find).
4. Interfoliado cronológico inverso unificado de publicaciones y comentarios (snscrape).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, Generator, Iterable, List, Optional, Sequence, Tuple, Union
from pydantic import BaseModel, Field


class CleanComment(BaseModel):
    """Modelo normalizado y saneado de comentario de Reddit."""
    id: str
    post_id: str = ""
    author: str = "[deleted]"
    body: str = ""
    score: int = 0
    created_utc: float = 0.0
    permalink: str = ""
    parent_id: Optional[str] = None
    is_pain_signal: bool = False
    matched_keywords: List[str] = Field(default_factory=list)


class CleanPost(BaseModel):
    """Modelo normalizado y saneado de publicación de Reddit."""
    id: str
    subreddit: str = ""
    title: str = ""
    selftext: str = ""
    author: str = "[deleted]"
    score: int = 0
    upvote_ratio: float = 0.0
    num_comments: int = 0
    created_utc: float = 0.0
    url: str = ""
    permalink: str = ""
    flair: str = ""
    comments: List[CleanComment] = Field(default_factory=list)
    is_pain_signal: bool = False
    matched_keywords: List[str] = Field(default_factory=list)


class UnifiedTimelineItem(BaseModel):
    """Elemento de línea temporal cronológica unificada (Post o Comentario)."""
    kind: str  # 'post' | 'comment'
    id: str
    author: str
    date_utc: datetime
    timestamp: float
    title_or_context: str
    body_text: str
    score: int
    url: str
    subreddit: str


class RedditNormalizer:
    """
    Motor de saneamiento, deduplicación y formateo estructural de datos de Reddit.
    """

    @staticmethod
    def normalize_id(raw_id: str) -> str:
        """
        Limpia y normaliza prefijos de tipo Thing de Reddit (t1_, t3_).
        Ejemplo: 't3_1abc23' -> '1abc23'.
        """
        if not raw_id:
            return ""
        clean = raw_id.strip()
        if clean.startswith(("t1_", "t2_", "t3_", "t4_", "t5_", "t6_")):
            return clean.split("_", 1)[1]
        return clean

    @staticmethod
    def is_deleted_or_removed(text: Optional[str]) -> bool:
        """Determina si un texto representa contenido eliminado por usuario o moderador."""
        if text is None:
            return True
        clean = text.strip()
        return clean in {"[deleted]", "[removed]", ""}

    @staticmethod
    def clean_text_body(text: Optional[str], max_length: Optional[int] = None) -> str:
        """
        Limpia texto de publicaciones o comentarios:
        - Normaliza espacios en blanco y saltos de línea repetidos.
        - Elimina marcadores de borrado.
        - Trunca opcionalmente para optimizar tokens.
        """
        if RedditNormalizer.is_deleted_or_removed(text):
            return ""
        cleaned = re.sub(r"\r\n|\r", "\n", text or "")
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        cleaned = cleaned.strip()
        if max_length and len(cleaned) > max_length:
            cleaned = cleaned[:max_length] + " [...]"
        return cleaned

    @staticmethod
    def deduplicate_posts(posts: Sequence[Union[CleanPost, Dict[str, Any]]]) -> List[Any]:
        """
        Deduplica una secuencia de publicaciones conservando el primer ítem encontrado
        y respetando el orden de mayor engagement/score.
        """
        seen_ids = set()
        deduped = []
        for p in posts:
            p_id = p.id if isinstance(p, CleanPost) else p.get("id", "")
            norm_id = RedditNormalizer.normalize_id(str(p_id))
            if norm_id and norm_id not in seen_ids:
                seen_ids.add(norm_id)
                deduped.append(p)
        return deduped

    @staticmethod
    def interleave_chronological(
        posts: Iterable[CleanPost],
        comments: Iterable[CleanComment]
    ) -> Generator[UnifiedTimelineItem, None, None]:
        """
        Algoritmo extraído de snscrape (_iter_api_submissions_and_comments).
        Intercala publicaciones y comentarios en una secuencia única ordenada
        en cronología inversa (los más recientes primero).
        Si un post y un comentario coinciden exactamente en timestamp,
        el comentario se emite primero por representar la reacción más granular.
        """
        post_iter = iter(sorted(posts, key=lambda p: p.created_utc, reverse=True))
        comment_iter = iter(sorted(comments, key=lambda c: c.created_utc, reverse=True))

        curr_post = next(post_iter, None)
        curr_comm = next(comment_iter, None)

        while curr_post is not None or curr_comm is not None:
            if curr_post is not None and curr_comm is not None:
                # Comentario primero en caso de empate
                if curr_post.created_utc > curr_comm.created_utc:
                    dt = datetime.fromtimestamp(curr_post.created_utc, tz=timezone.utc)
                    yield UnifiedTimelineItem(
                        kind="post",
                        id=curr_post.id,
                        author=curr_post.author,
                        date_utc=dt,
                        timestamp=curr_post.created_utc,
                        title_or_context=curr_post.title,
                        body_text=curr_post.selftext,
                        score=curr_post.score,
                        url=curr_post.permalink or curr_post.url,
                        subreddit=curr_post.subreddit
                    )
                    curr_post = next(post_iter, None)
                else:
                    dt = datetime.fromtimestamp(curr_comm.created_utc, tz=timezone.utc)
                    yield UnifiedTimelineItem(
                        kind="comment",
                        id=curr_comm.id,
                        author=curr_comm.author,
                        date_utc=dt,
                        timestamp=curr_comm.created_utc,
                        title_or_context=f"Comentario en post {curr_comm.post_id}",
                        body_text=curr_comm.body,
                        score=curr_comm.score,
                        url=curr_comm.permalink,
                        subreddit=""
                    )
                    curr_comm = next(comment_iter, None)
            elif curr_post is not None:
                dt = datetime.fromtimestamp(curr_post.created_utc, tz=timezone.utc)
                yield UnifiedTimelineItem(
                    kind="post",
                    id=curr_post.id,
                    author=curr_post.author,
                    date_utc=dt,
                    timestamp=curr_post.created_utc,
                    title_or_context=curr_post.title,
                    body_text=curr_post.selftext,
                    score=curr_post.score,
                    url=curr_post.permalink or curr_post.url,
                    subreddit=curr_post.subreddit
                )
                curr_post = next(post_iter, None)
            elif curr_comm is not None:
                dt = datetime.fromtimestamp(curr_comm.created_utc, tz=timezone.utc)
                yield UnifiedTimelineItem(
                    kind="comment",
                    id=curr_comm.id,
                    author=curr_comm.author,
                    date_utc=dt,
                    timestamp=curr_comm.created_utc,
                    title_or_context=f"Comentario en post {curr_comm.post_id}",
                    body_text=curr_comm.body,
                    score=curr_comm.score,
                    url=curr_comm.permalink,
                    subreddit=""
                )
                curr_comm = next(comment_iter, None)

    # ─── Formateo de Salida en Markdown Estructurado (reddit-find) ───

    @staticmethod
    def format_titles_table(
        topic: str,
        subreddits: Sequence[str],
        posts: Sequence[CleanPost]
    ) -> str:
        """
        Construye una tabla compacta en Markdown optimizada para escaneo rápido (Pass 1).
        Permite a analistas o LLMs evaluar decenas de posts con un coste mínimo de tokens.
        """
        subs_str = ", ".join(f"r/{s.removeprefix('r/')}" for s in subreddits)
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        lines = [
            f"# Escaneo Rápido de Títulos: {topic}",
            f"- **Subreddits:** {subs_str}",
            f"- **Fecha de Consulta:** {date_str} (UTC)",
            f"- **Publicaciones Totales:** {len(posts)}",
            "",
            "| Puntuación | Comentarios | Fecha (UTC) | Título | Señal Dolor | URL |",
            "|:---:|:---:|:---:|---|:---:|---|",
        ]

        sorted_posts = sorted(posts, key=lambda p: p.score, reverse=True)
        for p in sorted_posts:
            dt_str = (
                datetime.fromtimestamp(p.created_utc, tz=timezone.utc).strftime("%Y-%m-%d")
                if p.created_utc else "N/D"
            )
            safe_title = p.title.replace("|", "-").strip()
            pain_badge = "🔥 Sí" if p.is_pain_signal else "—"
            url_link = f"[Ver]({p.permalink or p.url})" if (p.permalink or p.url) else "N/D"
            lines.append(
                f"| {p.score} | {p.num_comments} | {dt_str} | {safe_title} | {pain_badge} | {url_link} |"
            )

        lines.extend([
            "",
            "---",
            "**Criterio de Selección:** Priorizar filas con `Puntuación > 20` o `Señal Dolor = 🔥 Sí` para análisis profundo.",
            ""
        ])

        return "\n".join(lines)

    @staticmethod
    def format_deep_dive_markdown(
        topic: str,
        subreddits: Sequence[str],
        posts: Sequence[CleanPost],
        max_comments_per_post: int = 8
    ) -> str:
        """
        Construye el informe estructurado en Markdown para análisis cualitativo profundo (Pass 2).
        Cada bloque de publicación incluye su metadato, contenido y comentarios más valiosos.
        """
        subs_str = ", ".join(f"r/{s.removeprefix('r/')}" for s in subreddits)
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        sections = [
            f"# Investigación Profunda de Reddit: {topic}",
            f"> Subreddits analizados: {subs_str} | Fecha: {date_str} | Hilos: {len(posts)}",
            "",
            "---",
            ""
        ]

        sorted_posts = sorted(posts, key=lambda p: p.score, reverse=True)

        for p in sorted_posts:
            dt_str = (
                datetime.fromtimestamp(p.created_utc, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
                if p.created_utc else "N/D"
            )
            pain_status = f" [Señales: {', '.join(p.matched_keywords)}]" if p.matched_keywords else ""

            block = [
                f"## [{p.score} pts] \"{p.title}\"{pain_status}",
                f"- **Comunidad:** r/{p.subreddit} | **Autor:** u/{p.author} | **Fecha:** {dt_str} UTC",
                f"- **Comentarios:** {p.num_comments} | **Enlace:** {p.permalink or p.url}"
            ]

            if p.selftext:
                block.append(f"\n**Contenido del Post:**\n{p.selftext}\n")

            if p.comments:
                block.append("**Comentarios Relevantes de la Comunidad:**")
                # Filtrar comentarios vacíos o borrados
                valid_comments = [c for c in p.comments if not RedditNormalizer.is_deleted_or_removed(c.body)]
                sorted_comments = sorted(valid_comments, key=lambda c: c.score, reverse=True)

                for c in sorted_comments[:max_comments_per_post]:
                    c_pain = f" *(Palabras: {', '.join(c.matched_keywords)})*" if c.matched_keywords else ""
                    block.append(f"- **[{c.score} pts]** u/{c.author}: {c.body}{c_pain}")

            block.append("\n---\n")
            sections.append("\n".join(block))

        return "\n".join(sections)
