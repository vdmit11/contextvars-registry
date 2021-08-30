until find . \( ! -regex '.*/\..*' \) \( -name '*.py' -or -name '*.rst' \) | entr -d make -C docs html; do sleep 1; done
