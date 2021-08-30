until find . \( ! -regex '.*/\..*' \) -name '*.rst' | entr -d make -C docs html; do sleep 1; done
