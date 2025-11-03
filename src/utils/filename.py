def construct_file_name(owner, repo, *file_details):
    return "_".join(map(str, [owner, repo, *file_details]))

